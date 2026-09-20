import unittest
from unittest.mock import patch

from backend.courseplatform.config import resolve_platform_url


class PlatformUrlConfigurationTests(unittest.TestCase):
    def test_explicit_platform_url_has_priority(self):
        with patch.dict(
            "os.environ",
            {
                "PLATFORM_URL": "https://learning.example.test/",
                "WHATSAPP_PLATFORM_URL": "https://whatsapp.example.test/",
                "VERCEL_PROJECT_PRODUCTION_URL": "project.vercel.app",
            },
            clear=True,
        ):
            self.assertEqual("https://learning.example.test", resolve_platform_url())

    def test_whatsapp_url_remains_compatible_fallback(self):
        with patch.dict(
            "os.environ",
            {
                "WHATSAPP_PLATFORM_URL": "https://legacy.example.test/",
                "VERCEL_PROJECT_PRODUCTION_URL": "project.vercel.app",
            },
            clear=True,
        ):
            self.assertEqual("https://legacy.example.test", resolve_platform_url())

    def test_vercel_production_hostname_gets_https_scheme(self):
        with patch.dict(
            "os.environ",
            {"VERCEL_PROJECT_PRODUCTION_URL": "project.vercel.app"},
            clear=True,
        ):
            self.assertEqual("https://project.vercel.app", resolve_platform_url())

    def test_missing_configuration_stays_empty_outside_vercel(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual("", resolve_platform_url())


if __name__ == "__main__":
    unittest.main()
