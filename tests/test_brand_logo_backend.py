import base64
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from backend.courseplatform import actions


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"institutional-logo"
PNG_DATA_URL = f"data:image/png;base64,{base64.b64encode(PNG_BYTES).decode('ascii')}"


class _Connection:
    def __init__(self):
        self.queries = []
        self.committed = False

    def execute(self, query, params=()):
        self.queries.append((" ".join(query.split()).lower(), params))

    def commit(self):
        self.committed = True


class BrandLogoBackendTests(unittest.TestCase):
    def test_brand_logo_upload_action_is_registered(self):
        self.assertIs(actions.ACTIONS["adminUploadBrandLogo"], actions.admin_upload_brand_logo)

    def test_raster_data_url_is_validated_and_canonicalized(self):
        mime_type, data_url, file_bytes = actions.decode_raster_data_url(
            PNG_DATA_URL,
            "image/png",
            actions.BRAND_LOGO_MAX_BYTES,
        )
        self.assertEqual(mime_type, "image/png")
        self.assertEqual(data_url, PNG_DATA_URL)
        self.assertEqual(file_bytes, PNG_BYTES)

    def test_raster_data_url_rejects_mismatched_file_signature(self):
        invalid = f"data:image/png;base64,{base64.b64encode(b'not-a-png').decode('ascii')}"
        with self.assertRaises(actions.ApiError) as error:
            actions.decode_raster_data_url(invalid, "image/png", actions.BRAND_LOGO_MAX_BYTES)
        self.assertEqual(error.exception.code, "INVALID_FILE_DATA")

    def test_admin_upload_persists_logo_and_preserves_gallery(self):
        database = _Connection()

        @contextmanager
        def fake_connection():
            yield database

        payload = {
            "courseId": "COURSE-1",
            "fileName": "logo.png",
            "mimeType": "image/png",
            "dataUrl": PNG_DATA_URL,
        }
        existing_media = {"logoUrl": "https://legacy.example/logo.png", "videos": [{"id": "VID-1"}]}
        with (
            patch.object(actions, "admin_context", return_value=("session", {"admin_id": "ADM-1"})),
            patch.object(actions, "read_media_config", return_value=existing_media),
            patch.object(actions, "upload_raster_asset_to_storage", return_value=(True, "")),
            patch.object(actions, "connection", fake_connection),
            patch.object(actions, "audit"),
        ):
            result = actions.admin_upload_brand_logo(payload)

        media = result["data"]["mediaConfig"]
        self.assertEqual(media["logoUrl"], PNG_DATA_URL)
        self.assertEqual(media["videos"], [{"id": "VID-1"}])
        self.assertTrue(result["data"]["storageSaved"])
        self.assertTrue(database.committed)
        self.assertTrue(any("insert into courseplatform.settings" in query for query, _ in database.queries))

    def test_media_configuration_rejects_active_content_instead_of_an_image(self):
        malicious = "data:image/svg+xml;base64,PHN2ZyBvbmxvYWQ9YWxlcnQoMSk+PC9zdmc+"
        with self.assertRaises(actions.ApiError) as error:
            actions.normalize_brand_logo_url(malicious)
        self.assertEqual(error.exception.code, "INVALID_BRAND_LOGO")


if __name__ == "__main__":
    unittest.main()
