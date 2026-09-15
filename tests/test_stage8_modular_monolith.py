import importlib
import json
import unittest
from pathlib import Path

from backend.courseplatform import actions, contracts
from backend.courseplatform.domains import identity
from backend.courseplatform.domains.registry import DOMAIN_ACTION_BINDINGS


ROOT = Path(__file__).resolve().parents[1]


class BackendModuleBoundaryTests(unittest.TestCase):
    def test_dispatcher_is_grouped_into_the_nine_expected_domains(self):
        self.assertEqual(
            {
                "identity",
                "catalog",
                "enrollments",
                "learning",
                "assessments",
                "certificates",
                "financial",
                "communication",
                "administration",
            },
            set(DOMAIN_ACTION_BINDINGS),
        )
        action_names = [name for bindings in DOMAIN_ACTION_BINDINGS.values() for name, _ in bindings]
        self.assertEqual(115, len(action_names))
        self.assertEqual(len(action_names), len(set(action_names)))
        self.assertEqual(set(action_names), set(actions.ACTIONS))
        self.assertTrue(all(callable(handler) for handler in actions.ACTIONS.values()))

    def test_legacy_action_contracts_are_reexported(self):
        self.assertIs(actions.ApiError, contracts.ApiError)
        self.assertIs(actions.normalize_email, identity.normalize_email)
        self.assertIs(actions.valid_password, identity.valid_password)
        self.assertIs(actions.ACTIONS["logout"], actions.ACTIONS["adminLogout"])

    def test_application_import_has_no_domain_cycle(self):
        module = importlib.import_module("backend.courseplatform.app")
        self.assertIsNotNone(module.app)

    def test_actions_uses_registry_instead_of_a_second_action_manifest(self):
        source = (ROOT / "backend" / "courseplatform" / "actions.py").read_text(encoding="utf-8")
        self.assertIn("ACTIONS = build_action_registry(globals())", source)
        self.assertNotIn("ACTIONS = {", source)
        self.assertLess(len(source.splitlines()), 11200)


class FrontendSourceTests(unittest.TestCase):
    def test_public_tree_matches_generated_distribution_tree(self):
        source_root = ROOT / "public"
        target_root = ROOT / "backend" / "courseplatform" / "static"
        source_files = sorted(path.relative_to(source_root) for path in source_root.rglob("*") if path.is_file())
        target_files = sorted(path.relative_to(target_root) for path in target_root.rglob("*") if path.is_file())
        self.assertEqual(source_files, target_files)
        for relative in source_files:
            self.assertEqual((source_root / relative).read_bytes(), (target_root / relative).read_bytes(), relative)

    def test_frontend_entrypoints_use_extracted_modules(self):
        admin_source = (ROOT / "public" / "admin.js").read_text(encoding="utf-8")
        student_source = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "public" / "assets" / "css" / "styles.css").read_text(encoding="utf-8")
        tokens = (ROOT / "public" / "assets" / "css" / "tokens.css").read_text(encoding="utf-8")
        self.assertIn("./admin/pagination.js", admin_source)
        self.assertIn("./student/routes.js", student_source)
        self.assertTrue(styles.startswith('@import url("./tokens.css");'))
        self.assertIn(":root {", tokens)
        self.assertNotRegex(styles, r"(?m)^:root\s*\{")

    def test_package_exposes_sync_and_parity_commands(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual("node scripts/sync_frontend.cjs", package["scripts"]["sync:frontend"])
        self.assertEqual("node scripts/sync_frontend.cjs --check", package["scripts"]["check:frontend"])


if __name__ == "__main__":
    unittest.main()
