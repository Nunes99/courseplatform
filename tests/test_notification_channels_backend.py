import json
import sys
import types
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

try:
    from psycopg.rows import dict_row as _dict_row  # noqa: F401
except (ImportError, ModuleNotFoundError):
    psycopg_stub = types.ModuleType("psycopg")
    psycopg_rows_stub = types.ModuleType("psycopg.rows")

    class _PsycopgError(Exception):
        pass

    psycopg_stub.Error = _PsycopgError
    psycopg_stub.OperationalError = _PsycopgError
    psycopg_stub.connect = None
    psycopg_rows_stub.dict_row = object()
    sys.modules["psycopg"] = psycopg_stub
    sys.modules["psycopg.rows"] = psycopg_rows_stub

from backend.courseplatform import actions


class _JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class _SmtpClient:
    def __init__(self):
        self.ehlo_count = 0
        self.tls_context = None
        self.credentials = None
        self.message = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def ehlo(self):
        self.ehlo_count += 1

    def starttls(self, context=None):
        self.tls_context = context

    def login(self, username, password):
        self.credentials = (username, password)

    def send_message(self, message):
        self.message = message


class NotificationChannelBackendTests(unittest.TestCase):
    def test_smtp_host_rejects_local_and_private_ip_targets(self):
        self.assertTrue(actions.valid_notification_host("smtp.example.org"))
        self.assertTrue(actions.valid_notification_host("8.8.8.8"))
        self.assertFalse(actions.valid_notification_host("localhost"))
        self.assertFalse(actions.valid_notification_host("127.0.0.1"))
        self.assertFalse(actions.valid_notification_host("10.0.0.5"))

    def test_student_dto_exposes_link_state_but_not_private_chat_id(self):
        public = actions.public_student({
            "student_id": "STU-1", "telegram_chat_id": "123456789",
            "telegram_opt_in": True,
        })
        self.assertTrue(public["telegramLinked"])
        self.assertTrue(public["telegramOptIn"])
        self.assertNotIn("telegramChatId", public)

    def test_provider_error_redaction_removes_bot_tokens(self):
        token = "123456789:abcdefghijklmnopqrstuvwxyz_123456"
        safe = actions.redact_notification_error(f"request /bot{token}/sendMessage Bearer {token}", token)
        self.assertNotIn(token, safe)
        self.assertIn("[redacted]", safe)

    def test_public_channel_configurations_never_return_secrets(self):
        with patch.object(actions, "email_runtime_configuration", return_value={
            "configured": True, "smtpPassword": "smtp-secret", "timeoutSeconds": 12,
            "passwordConfigured": True,
        }):
            public_email = actions.email_configuration()
        with patch.object(actions, "telegram_runtime_configuration", return_value={
            "configured": True, "botToken": "telegram-secret", "timeoutSeconds": 12,
            "tokenConfigured": True,
        }):
            public_telegram = actions.telegram_configuration()
        self.assertNotIn("smtpPassword", public_email)
        self.assertNotIn("botToken", public_telegram)
        self.assertNotIn("timeoutSeconds", public_email)
        self.assertNotIn("timeoutSeconds", public_telegram)

    def test_email_send_uses_starttls_authentication_and_message_id(self):
        configuration = {
            "configured": True,
            "smtpHost": "smtp.example.org",
            "smtpPort": 587,
            "smtpUsername": "mailer@example.org",
            "smtpPassword": "server-only",
            "fromEmail": "mailer@example.org",
            "fromName": "Formação",
            "useTls": True,
            "timeoutSeconds": 5,
        }
        delivery = {
            "recipient": "student@example.org",
            "student_name": "Ana",
            "title": "Módulo disponível",
            "message": "Já pode começar.",
            "action_url": "https://formacao.example.org/#/lessons",
        }
        client = _SmtpClient()
        with (
            patch.object(actions.smtplib, "SMTP", return_value=client) as smtp,
            patch.object(actions.ssl, "create_default_context", return_value=object()),
        ):
            provider_id = actions.send_email_notification(delivery, configuration)
        smtp.assert_called_once()
        self.assertIsNotNone(client.tls_context)
        self.assertEqual(client.credentials, ("mailer@example.org", "server-only"))
        self.assertEqual(client.message["To"], "student@example.org")
        self.assertNotIn("server-only", client.message.as_string())
        self.assertTrue(provider_id)

    def test_email_port_465_uses_smtp_ssl(self):
        configuration = {
            "configured": True,
            "smtpHost": "smtp.example.org",
            "smtpPort": 465,
            "smtpUsername": "",
            "smtpPassword": "",
            "fromEmail": "mailer@example.org",
            "fromName": "Formação",
            "useTls": True,
            "timeoutSeconds": 5,
        }
        client = _SmtpClient()
        with (
            patch.object(actions.smtplib, "SMTP_SSL", return_value=client) as smtp_ssl,
            patch.object(actions.smtplib, "SMTP") as smtp,
            patch.object(actions.ssl, "create_default_context", return_value=object()),
        ):
            actions.send_email_notification({
                "recipient": "student@example.org", "title": "Teste", "message": "Mensagem"
            }, configuration)
        smtp_ssl.assert_called_once()
        smtp.assert_not_called()
        self.assertIsNone(client.tls_context)

    def test_telegram_send_posts_chat_id_and_returns_message_id(self):
        configuration = {
            "configured": True,
            "botToken": "123456789:abcdefghijklmnopqrstuvwxyz_123456",
            "parseMode": "HTML",
            "timeoutSeconds": 5,
        }
        delivery = {
            "recipient": "1001234567890", "student_name": "Ana",
            "title": "Avaliação concluída", "message": "Consulte o resultado.",
            "action_url": "https://formacao.example.org/#/notifications",
        }
        with patch.object(
            actions.urllib.request, "urlopen",
            return_value=_JsonResponse({"ok": True, "result": {"message_id": 812}}),
        ) as urlopen:
            provider_id = actions.send_telegram_notification(delivery, configuration)
        self.assertEqual(provider_id, "812")
        request = urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["chat_id"], "1001234567890")
        self.assertEqual(body["parse_mode"], "HTML")

    def test_notification_queues_selected_channels_with_independent_consent(self):
        student = {
            "student_id": "STU-1", "email": "ana@example.org", "phone": "+258840000000",
            "telegram_chat_id": "123456789", "whatsapp_opt_in": True,
            "email_opt_in": False, "telegram_opt_in": True,
            "notification_preferences_json": {"GENERAL": True},
        }

        class _Cursor:
            def __init__(self, row=None):
                self.row = row

            def fetchone(self):
                return self.row

        class _Connection:
            def __init__(self):
                self.deliveries = []

            def execute(self, query, params=()):
                if query.strip().lower().startswith("select * from courseplatform.students"):
                    return _Cursor(student)
                if "insert into courseplatform.notification_deliveries" in query:
                    self.deliveries.append(params)
                return _Cursor()

        database = _Connection()
        actions.create_student_notification(
            database, "STU-1", "GENERAL", "Título", "Mensagem",
            send_whatsapp=True, send_email=True, send_telegram=True,
        )
        by_channel = {params[2]: params for params in database.deliveries}
        self.assertEqual(by_channel["WHATSAPP"][4], "PENDING")
        self.assertEqual(by_channel["EMAIL"][4], "SKIPPED")
        self.assertEqual(by_channel["TELEGRAM"][4], "PENDING")

    def test_telegram_link_is_short_one_time_and_requires_bot_start(self):
        class _Cursor:
            def fetchone(self):
                return None

        class _Connection:
            def __init__(self):
                self.params = []

            def execute(self, _query, params=()):
                self.params.append(params)
                return _Cursor()

            def commit(self):
                pass

        database = _Connection()

        @contextmanager
        def fake_connection():
            yield database

        with (
            patch.object(actions, "prepare_notification_feature_schema"),
            patch.object(actions, "student_context", return_value=("session", {"student_id": "STU-1"})),
            patch.object(actions, "telegram_runtime_configuration", return_value={
                "configured": True, "botUsername": "CoursePlatformBot"
            }),
            patch.object(actions, "connection", fake_connection),
        ):
            result = actions.student_start_telegram_link({"sessionToken": "session"})["data"]
        self.assertTrue(result["linkUrl"].startswith("https://t.me/CoursePlatformBot?start="))
        self.assertLessEqual(len(result["linkToken"]), 64)
        self.assertNotIn(result["linkToken"], str(database.params))

    def test_telegram_link_processor_accepts_only_private_positive_chat(self):
        token = "abcdefghijklmnopqrstuvwx"

        class _Cursor:
            def __init__(self, row=None):
                self.row = row

            def fetchone(self):
                return self.row

        class _Connection:
            def __init__(self):
                self.executed = []

            def execute(self, query, params=()):
                self.executed.append((query, params))
                if "select * from courseplatform.telegram_link_tokens" in query:
                    return _Cursor({"student_id": "STU-1"})
                return _Cursor()

            def commit(self):
                pass

        database = _Connection()

        @contextmanager
        def fake_connection():
            yield database

        updates = [
            {
                "update_id": 10,
                "message": {"text": f"/start {token}", "chat": {"id": 123456789, "type": "private"}},
            },
            {
                "update_id": 11,
                "message": {"text": f"/start {token}", "chat": {"id": -100123456, "type": "group"}},
            },
        ]
        with (
            patch.object(actions, "fetch_one", return_value={"cursor_value": 0}),
            patch.object(actions, "telegram_get_updates", return_value=updates),
            patch.object(actions, "connection", fake_connection),
        ):
            linked = actions.process_telegram_link_updates({"configured": True, "botToken": "hidden"})
        self.assertEqual(linked, 1)
        student_updates = [
            params for query, params in database.executed
            if "update courseplatform.students" in query
        ]
        self.assertEqual(student_updates, [("123456789", "STU-1")])
        cursor_updates = [
            params for query, params in database.executed
            if "insert into courseplatform.notification_channel_state" in query
        ]
        self.assertEqual(cursor_updates, [(12,)])

    def test_admin_secrets_require_strong_shared_encryption_key(self):
        settings = SimpleNamespace(notification_config_encryption_key="short")
        common = (
            patch.object(actions, "admin_context", return_value=("session", {"admin_id": "ADM-1"})),
            patch.object(actions, "prepare_notification_feature_schema"),
            patch.object(actions, "get_settings", return_value=settings),
        )
        with common[0], common[1], common[2]:
            with self.assertRaises(actions.ApiError) as email_error:
                actions.admin_save_email_configuration({"emailConfiguration": {"smtpPassword": "secret"}})
        self.assertEqual(email_error.exception.code, "WEAK_NOTIFICATION_ENCRYPTION_KEY")

        with (
            patch.object(actions, "admin_context", return_value=("session", {"admin_id": "ADM-1"})),
            patch.object(actions, "prepare_notification_feature_schema"),
            patch.object(actions, "get_settings", return_value=settings),
        ):
            with self.assertRaises(actions.ApiError) as telegram_error:
                actions.admin_save_telegram_configuration({
                    "telegramConfiguration": {"botToken": "123456:abcdefghijklmnopqrstuvwxyz"}
                })
        self.assertEqual(telegram_error.exception.code, "WEAK_NOTIFICATION_ENCRYPTION_KEY")


if __name__ == "__main__":
    unittest.main()
