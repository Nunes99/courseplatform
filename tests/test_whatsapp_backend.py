import json
import sys
import types
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

# These tests exercise pure notification logic and use mocked database calls. The
# fallback keeps them runnable in minimal CI jobs that have not installed psycopg.
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


class _HttpResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class WhatsAppBackendTests(unittest.TestCase):
    def test_public_configuration_never_contains_runtime_secret(self):
        runtime = {
            "enabled": True,
            "configured": True,
            "accessToken": "secret-token",
            "timeoutSeconds": 12,
            "tokenConfigured": True,
        }
        with patch.object(actions, "whatsapp_runtime_configuration", return_value=runtime):
            public = actions.whatsapp_configuration()
        self.assertNotIn("accessToken", public)
        self.assertNotIn("timeoutSeconds", public)
        self.assertTrue(public["tokenConfigured"])

    def test_platform_url_requires_a_complete_url_without_credentials(self):
        self.assertTrue(actions.valid_whatsapp_platform_url("https://formacao.example.org"))
        self.assertTrue(actions.valid_whatsapp_platform_url("http://localhost:8000"))
        self.assertFalse(actions.valid_whatsapp_platform_url("https://"))
        self.assertFalse(actions.valid_whatsapp_platform_url("javascript:alert(1)"))
        self.assertFalse(actions.valid_whatsapp_platform_url("https://user:password@example.org"))

    def test_template_send_uses_server_token_and_returns_provider_id(self):
        configuration = {
            "configured": True,
            "graphApiVersion": "v23.0",
            "phoneNumberId": "123456789",
            "platformUrl": "https://formacao.example.org",
            "templateName": "student_update",
            "templateLanguage": "pt_PT",
            "accessToken": "server-only-token",
            "timeoutSeconds": 5,
        }
        delivery = {
            "recipient": "258840000000",
            "student_name": "Estudante",
            "title": "Módulo disponível",
            "message": "O conteúdo já pode ser consultado.",
            "action_url": "#/lessons",
        }
        with patch.object(
            actions.urllib.request,
            "urlopen",
            return_value=_HttpResponse({"messages": [{"id": "wamid.123"}]}),
        ) as urlopen:
            message_id = actions.send_whatsapp_template(delivery, configuration)

        self.assertEqual(message_id, "wamid.123")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.headers["Authorization"], "Bearer server-only-token")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["to"], "258840000000")
        self.assertEqual(body["template"]["name"], "student_update")

    def test_template_send_rejects_success_response_without_message_id(self):
        configuration = {
            "configured": True,
            "graphApiVersion": "v23.0",
            "phoneNumberId": "123456789",
            "platformUrl": "https://formacao.example.org",
            "templateName": "student_update",
            "templateLanguage": "pt_PT",
            "accessToken": "server-only-token",
            "timeoutSeconds": 5,
        }
        delivery = {
            "recipient": "258840000000",
            "student_name": "Estudante",
            "title": "Atualização",
            "message": "Mensagem",
            "action_url": "#/notifications",
        }
        with patch.object(
            actions.urllib.request,
            "urlopen",
            return_value=_HttpResponse({"messages": []}),
        ):
            with self.assertRaisesRegex(RuntimeError, "identificador"):
                actions.send_whatsapp_template(delivery, configuration)

    def test_delivery_claim_uses_database_lock_and_processing_lease(self):
        class _Cursor:
            def fetchall(self):
                return [{"delivery_id": "NDL-1"}]

        class _Connection:
            def __init__(self):
                self.query = ""
                self.params = ()
                self.committed = False

            def execute(self, query, params):
                self.query = query
                self.params = params
                return _Cursor()

            def commit(self):
                self.committed = True

        database = _Connection()

        @contextmanager
        def fake_connection():
            yield database

        with patch.object(actions, "connection", fake_connection):
            rows = actions.claim_whatsapp_deliveries(["NTF-1"], 7)

        self.assertEqual(rows, [{"delivery_id": "NDL-1"}])
        normalized_query = " ".join(database.query.lower().split())
        self.assertIn("for update of d skip locked", normalized_query)
        self.assertIn("set status = 'processing'", normalized_query)
        self.assertIn("d.status = 'processing'", normalized_query)
        self.assertIn("interval '5 minutes'", normalized_query)
        self.assertEqual(database.params, ("WHATSAPP", ["NTF-1"], 7))
        self.assertTrue(database.committed)

    def test_admin_token_requires_a_strong_server_encryption_key(self):
        settings = SimpleNamespace(whatsapp_config_encryption_key="short")
        payload = {
            "whatsappConfiguration": {
                "accessToken": "token-to-protect",
                "graphApiVersion": "v23.0",
                "templateLanguage": "pt_PT",
            }
        }
        with (
            patch.object(actions, "admin_context", return_value=("session", {"admin_id": "ADM-1"})),
            patch.object(actions, "prepare_notification_feature_schema"),
            patch.object(actions, "get_settings", return_value=settings),
        ):
            with self.assertRaises(actions.ApiError) as error:
                actions.admin_save_whatsapp_configuration(payload)
        self.assertEqual(error.exception.code, "WEAK_WHATSAPP_ENCRYPTION_KEY")

    def test_admin_configuration_rejects_incomplete_platform_url(self):
        settings = SimpleNamespace(whatsapp_config_encryption_key="x" * 32)
        payload = {
            "whatsappConfiguration": {
                "platformUrl": "https://",
                "graphApiVersion": "v23.0",
                "templateLanguage": "pt_PT",
            }
        }
        with (
            patch.object(actions, "admin_context", return_value=("session", {"admin_id": "ADM-1"})),
            patch.object(actions, "prepare_notification_feature_schema"),
            patch.object(actions, "get_settings", return_value=settings),
        ):
            with self.assertRaises(actions.ApiError) as error:
                actions.admin_save_whatsapp_configuration(payload)
        self.assertEqual(error.exception.code, "INVALID_WHATSAPP_PLATFORM_URL")


if __name__ == "__main__":
    unittest.main()
