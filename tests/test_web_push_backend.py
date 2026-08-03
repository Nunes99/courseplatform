import json
import base64
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.courseplatform import actions


class _Cursor:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _TemplateConnection:
    def __init__(self, row=None):
        self.row = row

    def execute(self, query, _params=()):
        if "courseplatform.notification_templates" in query:
            return _Cursor(self.row)
        return _Cursor()


class WebPushBackendTests(unittest.TestCase):
    def test_vapid_and_subscription_validators_reject_unsafe_values(self):
        self.assertTrue(actions.valid_vapid_subject("mailto:suporte@example.org"))
        self.assertTrue(actions.valid_vapid_subject("https://example.org/contacto"))
        self.assertFalse(actions.valid_vapid_subject("http://example.org"))
        self.assertFalse(actions.valid_vapid_subject("https://user:secret@example.org"))
        self.assertTrue(actions.valid_push_endpoint("https://push.example.org/send/abc"))
        self.assertFalse(actions.valid_push_endpoint("http://push.example.org/send/abc"))
        self.assertFalse(actions.valid_push_endpoint("javascript:alert(1)"))
        public_key = base64.urlsafe_b64encode(b"\x04" + b"p" * 64).rstrip(b"=").decode("ascii")
        private_key = base64.urlsafe_b64encode(b"s" * 32).rstrip(b"=").decode("ascii")
        self.assertTrue(actions.valid_vapid_key(public_key, 65, require_uncompressed_point=True))
        self.assertTrue(actions.valid_vapid_key(private_key, 32))
        self.assertFalse(actions.valid_vapid_key(private_key, 65, require_uncompressed_point=True))

    def test_public_push_configuration_never_exposes_server_secrets(self):
        runtime = {
            "enabled": True,
            "configured": True,
            "publicKey": "public-vapid-key",
            "privateKey": "private-vapid-key",
            "encryptionKey": "database-encryption-key",
            "ttlSeconds": 86400,
            "subject": "mailto:suporte@example.org",
        }
        with patch.object(actions, "web_push_runtime_configuration", return_value=runtime):
            public = actions.web_push_configuration()
        self.assertEqual(public["publicKey"], "public-vapid-key")
        self.assertNotIn("privateKey", public)
        self.assertNotIn("encryptionKey", public)
        self.assertNotIn("ttlSeconds", public)

    def test_channel_specific_templates_are_rendered_and_snapshotted(self):
        row = {
            "template_key": "MODULE_ACCESS_UPDATED",
            "internal_title_template": "Módulo: {{module}}",
            "internal_message_template": "Estado interno: {{status}}",
            "email_subject_template": "Email sobre {{module}}",
            "email_message_template": "Olá, {{student_name}}. {{details}}",
            "push_title_template": "{{module}} disponível",
            "push_message_template": "Toque para abrir: {{action_url}}",
        }
        content = actions.resolve_notification_content(
            _TemplateConnection(row),
            "MODULE_ACCESS_UPDATED",
            {
                "student_name": "Ana",
                "module": "Segurança industrial",
                "status": "Disponível",
                "details": "Pode iniciar a leitura.",
                "action_url": "#/lesson/LESSON-1",
            },
            "Título alternativo",
            "Mensagem alternativa",
        )
        self.assertEqual(content["title"], "Módulo: Segurança industrial")
        self.assertEqual(content["emailSubject"], "Email sobre Segurança industrial")
        self.assertEqual(content["emailMessage"], "Olá, Ana. Pode iniciar a leitura.")
        self.assertEqual(content["pushTitle"], "Segurança industrial disponível")
        self.assertEqual(content["pushMessage"], "Toque para abrir: #/lesson/LESSON-1")
        self.assertEqual(content["templateKey"], "MODULE_ACCESS_UPDATED")

    def test_web_push_uses_vapid_and_channel_specific_copy(self):
        response = SimpleNamespace(status_code=201)
        webpush = MagicMock(return_value=response)
        subscriptions = [{
            "subscription_id": "PSH-1",
            "endpoint": "https://push.example.org/send/abc",
            "p256dh": "A" * 87,
            "auth": "B" * 22,
        }]
        configuration = {
            "configured": True,
            "privateKey": "private-vapid-key",
            "subject": "mailto:suporte@example.org",
            "platformUrl": "https://formacao.example.org",
            "ttlSeconds": 86400,
            "timeoutSeconds": 12,
            "encryptionKey": "x" * 32,
        }
        delivery = {
            "notification_id": "NTF-1",
            "student_id": "STU-1",
            "title": "Título interno",
            "message": "Mensagem interna",
            "push_title": "Título Push",
            "push_message": "Mensagem Push",
            "action_url": "#/notifications",
            "priority": "HIGH",
        }
        with (
            patch.object(actions, "webpush", webpush),
            patch.object(actions, "push_subscriptions_for_student", return_value=subscriptions),
            patch.object(actions, "update_push_subscription_delivery") as update,
            patch.object(actions, "student_unread_badge_count", return_value=7),
        ):
            provider_id = actions.send_web_push_notification(delivery, configuration)
        self.assertEqual(provider_id, "1 dispositivo(s)")
        call = webpush.call_args.kwargs
        payload = json.loads(call["data"])
        self.assertEqual(payload["title"], "Título Push")
        self.assertEqual(payload["body"], "Mensagem Push")
        self.assertEqual(payload["url"], "https://formacao.example.org/#/notifications")
        self.assertEqual(payload["badgeCount"], 7)
        self.assertEqual(call["vapid_private_key"], "private-vapid-key")
        self.assertEqual(call["vapid_claims"], {"sub": "mailto:suporte@example.org"})
        self.assertEqual(call["ttl"], 86400)
        self.assertEqual(call["timeout"], 12)
        update.assert_called_once_with("PSH-1", True)


if __name__ == "__main__":
    unittest.main()
