import importlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.courseplatform.certificate_pdf import CertificateLayoutError

api = importlib.import_module('backend.courseplatform.app')


class CertificatePdfRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        self.data = json.loads((Path(__file__).parent / 'fixtures/professional_certificate.json').read_text(encoding='utf-8'))

    def test_preview_assets_have_browser_compatible_types(self):
        for path, content_type in [('/vendor/qrcode-generator.mjs', 'text/javascript'), ('/assets/fonts/Vera.ttf', 'font/ttf')]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(content_type, response.headers['content-type'])

    def test_invalid_layout_does_not_consume_a_download(self):
        result = {'model': 'professional', 'certificate': {'certificateNumber': 'DEMO'}, 'pdfData': self.data}
        with patch.object(api, 'certificate_pdf_payload', return_value=result), patch.object(api, 'build_course_certificate_pdf', side_effect=CertificateLayoutError('Texto demasiado longo.')), patch.object(api, 'record_certificate_download') as record:
            response = self.client.get('/api/certificates/DEMO/pdf', headers={'x-session-token': 'test-only'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'CERTIFICATE_LAYOUT_INVALID')
        record.assert_not_called()

    def test_admin_pdf_uses_saved_payload_without_student_download_charge(self):
        result = {'model': 'professional', 'certificate': {'certificateNumber': 'DEMO'}, 'pdfData': self.data}
        with patch.object(api, 'admin_certificate_pdf_payload', return_value=result) as payload, patch.object(api, 'record_certificate_download') as record:
            response = self.client.get('/api/certificates/DEMO/pdf', headers={'x-admin-token': 'test-only'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertEqual(payload.call_args.args[0]['certificateId'], 'DEMO')
        record.assert_not_called()


if __name__ == '__main__':
    unittest.main()
