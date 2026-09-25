import inspect
import unittest
from pathlib import Path

from backend.courseplatform.domains import catalog


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20260925071234_add_versioned_question_bank.sql"


class QuestionBankValidationTests(unittest.TestCase):
    def test_objective_question_is_normalized_with_metadata(self):
        result = catalog.normalize_question_bank_draft({
            "title": "Capital de Moçambique", "questionType": "single_choice",
            "prompt": "Qual é a capital de Moçambique?", "difficulty": "easy",
            "tags": ["Geografia", " geografia ", "Moçambique"], "points": 2,
            "explanation": "Maputo é a capital.",
            "options": [{"optionText": "Maputo", "isCorrect": True}, {"optionText": "Beira", "isCorrect": False}],
        })
        self.assertEqual("SINGLE_CHOICE", result["questionType"])
        self.assertEqual("EASY", result["difficulty"])
        self.assertEqual(["geografia", "moçambique"], result["tags"])
        self.assertEqual(1, sum(option["isCorrect"] for option in result["options"]))

    def test_single_choice_rejects_multiple_correct_options(self):
        with self.assertRaises(catalog.ApiError) as raised:
            catalog.normalize_question_bank_draft({
                "title": "Questão inválida", "questionType": "SINGLE_CHOICE",
                "prompt": "Escolha uma resposta.", "difficulty": "MEDIUM", "points": 1,
                "options": [{"optionText": "A", "isCorrect": True}, {"optionText": "B", "isCorrect": True}],
            })
        self.assertEqual("QUESTION_BANK_CORRECT_OPTION_INVALID", raised.exception.code)

    def test_subjective_question_rejects_options(self):
        with self.assertRaises(catalog.ApiError) as raised:
            catalog.normalize_question_bank_draft({
                "title": "Resposta longa", "questionType": "LONG_TEXT", "prompt": "Explique o conceito.",
                "difficulty": "HARD", "points": 5,
                "options": [{"optionText": "Não permitido", "isCorrect": True}],
            })
        self.assertEqual("QUESTION_BANK_OPTIONS_NOT_ALLOWED", raised.exception.code)

    def test_incomplete_objective_draft_can_be_saved_but_not_published(self):
        payload = {
            "title": "Questão em preparação", "questionType": "SINGLE_CHOICE",
            "prompt": "Enunciado ainda em revisão.", "difficulty": "MEDIUM", "points": 1,
            "options": [],
        }
        result = catalog.normalize_question_bank_draft(payload, require_publishable=False)
        self.assertEqual([], result["options"])
        with self.assertRaises(catalog.ApiError) as raised:
            catalog.normalize_question_bank_draft(payload)
        self.assertEqual("QUESTION_BANK_OPTIONS_REQUIRED", raised.exception.code)

    def test_list_contract_does_not_serialize_answer_keys(self):
        source = inspect.getsource(catalog.admin_list_question_bank_action)
        self.assertNotIn('"correctAnswer"', source)
        self.assertNotIn('"isCorrect"', source)
        self.assertIn('"publishedVersion"', source)


class QuestionBankMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8").lower()

    def test_migration_is_additive_and_records_schema_version(self):
        self.assertIn("create table if not exists courseplatform.question_bank_items", self.sql)
        self.assertIn("create table if not exists courseplatform.question_bank_versions", self.sql)
        self.assertIn("create table if not exists courseplatform.question_bank_options", self.sql)
        self.assertIn("20260925130000", self.sql)
        self.assertNotIn("drop table", self.sql)

    def test_published_versions_and_options_are_immutable(self):
        self.assertIn("protect_published_question_bank_version", self.sql)
        self.assertIn("protect_published_question_bank_option", self.sql)
        self.assertIn("before insert or update or delete", self.sql)

    def test_browser_roles_have_no_question_bank_privileges(self):
        for table in ("question_bank_items", "question_bank_versions", "question_bank_options"):
            self.assertIn(f"revoke all privileges on courseplatform.{table} from public, anon, authenticated", self.sql)
        self.assertIn("alter table courseplatform.question_bank_items enable row level security", self.sql)


class QuestionBankFrontendContractTests(unittest.TestCase):
    def test_admin_supports_authoring_publishing_and_snapshot_attachment(self):
        admin_source = (ROOT / "public" / "admin.js").read_text(encoding="utf-8")
        api_source = (ROOT / "public" / "api.js").read_text(encoding="utf-8")
        self.assertIn("Banco de questões", admin_source)
        self.assertIn("data-publish-bank-version", admin_source)
        self.assertIn("data-attach-bank-question", admin_source)
        self.assertIn("adminSaveQuestionBankDraft", api_source)
        self.assertIn("adminAttachQuestionBankVersion", api_source)


if __name__ == "__main__":
    unittest.main()
