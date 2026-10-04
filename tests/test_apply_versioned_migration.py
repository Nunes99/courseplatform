import tempfile
import unittest
from pathlib import Path

from scripts.apply_versioned_migration import MIGRATIONS, migration_metadata


class VersionedMigrationApplyTests(unittest.TestCase):
    def test_metadata_accepts_reviewed_migration_in_canonical_directory(self):
        path = MIGRATIONS / "20261004063506_add_multi_tenant_foundation.sql"

        resolved, version, name, digest = migration_metadata(path)

        self.assertEqual(path.resolve(), resolved)
        self.assertEqual("20261004063506", version)
        self.assertEqual("add_multi_tenant_foundation", name)
        self.assertEqual(64, len(digest))

    def test_metadata_rejects_migration_outside_canonical_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "20261004063506_not_allowed.sql"
            path.write_text("select 1;", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "supabase/migrations"):
                migration_metadata(path)


if __name__ == "__main__":
    unittest.main()
