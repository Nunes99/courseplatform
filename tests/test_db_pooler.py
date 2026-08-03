import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.courseplatform import db


class DatabasePoolerTests(unittest.TestCase):
    def test_connections_disable_named_prepared_statements(self):
        settings = SimpleNamespace(
            database_url="postgresql://example.invalid/database",
            db_connect_timeout=5,
            db_connect_retries=1,
            require_database=lambda: None,
        )
        sentinel = object()
        with (
            patch.object(db, "get_settings", return_value=settings),
            patch.object(db.psycopg, "connect", return_value=sentinel) as connect,
        ):
            result = db._connect()

        self.assertIs(result, sentinel)
        self.assertIsNone(connect.call_args.kwargs["prepare_threshold"])


if __name__ == "__main__":
    unittest.main()
