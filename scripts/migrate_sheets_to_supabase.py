import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:
    psycopg = None

    class Jsonb:
        def __init__(self, value):
            self.value = value

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

EXCEL_MAIN_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
EXCEL_REL_NS = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
EXCEL_PACKAGE_REL_NS = {"pr": "http://schemas.openxmlformats.org/package/2006/relationships"}

TABLES = [
    ("StudentImport", "student_import", {
        "__rowId": "row_id",
        "__rowNumber": "source_row",
        "fullName": "full_name",
        "email": "email",
        "country": "country",
        "organization": "organization",
        "processed": "processed",
    }, "row_id"),
    ("StudentImportResults", "student_import_results", {
        "__rowId": "row_id",
        "importId": "import_id",
        "sourceRow": "source_row",
        "success": "success",
        "fullName": "full_name",
        "email": "email",
        "studentId": "student_id",
        "error": "error",
        "importedAt": "imported_at",
    }, "row_id"),
    ("Students", "students", {
        "studentId": "student_id",
        "publicStudentId": "public_student_id",
        "fullName": "full_name",
        "email": "email",
        "status": "status",
        "country": "country",
        "organization": "organization",
        "phone": "phone",
        "jobTitle": "job_title",
        "interests": "interests",
        "profilePhotoUrl": "profile_photo_url",
        "createdAt": "created_at",
        "updatedAt": "updated_at",
        "lastLoginAt": "last_login_at",
    }, "student_id"),
    ("Admins", "admins", {
        "adminId": "admin_id",
        "fullName": "full_name",
        "email": "email",
        "role": "role",
        "status": "status",
        "createdAt": "created_at",
        "updatedAt": "updated_at",
    }, "admin_id"),
    ("NewCredentials", "new_credentials", {
        "batchId": "batch_id",
        "credentialId": "credential_id",
        "sourceRow": "source_row",
        "studentId": "student_id",
        "fullName": "full_name",
        "email": "email",
        "generatedAt": "generated_at",
        "status": "status",
    }, "credential_id"),
    ("Sessions", "sessions", {
        "sessionToken": "session_token",
        "studentId": "subject_id",
        "createdAt": "created_at",
        "expiresAt": "expires_at",
        "active": "active",
        "userAgent": "user_agent",
        "ipHash": "ip_hash",
        "revokedAt": "revoked_at",
    }, "session_token"),
    ("Courses", "courses", {
        "courseId": "course_id",
        "courseCode": "course_code",
        "title": "title",
        "description": "description",
        "totalHours": "total_hours",
        "passingScore": "passing_score",
        "status": "status",
        "createdAt": "created_at",
        "updatedAt": "updated_at",
    }, "course_id"),
    ("Lessons", "lessons", {
        "lessonId": "lesson_id",
        "courseId": "course_id",
        "lessonNumber": "lesson_number",
        "title": "title",
        "slug": "slug",
        "summary": "summary",
        "theoryMinutes": "theory_minutes",
        "exerciseMinutes": "exercise_minutes",
        "individualMinutes": "individual_minutes",
        "passingScore": "passing_score",
        "prerequisiteLessonId": "prerequisite_lesson_id",
        "status": "status",
        "createdAt": "created_at",
        "updatedAt": "updated_at",
    }, "lesson_id"),
    ("LessonContent", "lesson_content", {
        "contentId": "content_id",
        "lessonId": "lesson_id",
        "sectionOrder": "section_order",
        "sectionType": "section_type",
        "title": "title",
        "bodyHtml": "body_html",
        "estimatedMinutes": "estimated_minutes",
        "isRequired": "is_required",
        "status": "status",
        "createdAt": "created_at",
        "updatedAt": "updated_at",
    }, "content_id"),
    ("Questions", "questions", {
        "questionId": "question_id",
        "lessonId": "lesson_id",
        "questionOrder": "question_order",
        "questionType": "question_type",
        "prompt": "prompt",
        "points": "points",
        "correctAnswer": "correct_answer",
        "explanation": "explanation",
        "isRequired": "is_required",
        "status": "status",
        "createdAt": "created_at",
        "updatedAt": "updated_at",
    }, "question_id"),
    ("QuestionOptions", "question_options", {
        "optionId": "option_id",
        "questionId": "question_id",
        "optionOrder": "option_order",
        "optionLabel": "option_label",
        "optionText": "option_text",
        "isCorrect": "is_correct",
        "createdAt": "created_at",
    }, "option_id"),
    ("Groups", "groups", {
        "groupId": "group_id",
        "groupCode": "group_code",
        "name": "name",
        "courseId": "course_id",
        "startDate": "start_date",
        "endDate": "end_date",
        "status": "status",
        "createdAt": "created_at",
        "updatedAt": "updated_at",
    }, "group_id"),
    ("Enrollments", "enrollments", {
        "enrollmentId": "enrollment_id",
        "studentId": "student_id",
        "courseId": "course_id",
        "groupId": "group_id",
        "status": "status",
        "enrolledAt": "enrolled_at",
        "completedAt": "completed_at",
        "progressPercent": "progress_percent",
        "finalScore": "final_score",
        "certificateId": "certificate_id",
        "updatedAt": "updated_at",
    }, "enrollment_id"),
    ("GroupMembers", "group_members", {
        "groupMemberId": "group_member_id",
        "groupId": "group_id",
        "studentId": "student_id",
        "status": "status",
        "joinedAt": "joined_at",
        "updatedAt": "updated_at",
    }, "group_member_id"),
    ("LessonProgress", "lesson_progress", {
        "progressId": "progress_id",
        "enrollmentId": "enrollment_id",
        "studentId": "student_id",
        "lessonId": "lesson_id",
        "status": "status",
        "unlockedAt": "unlocked_at",
        "startedAt": "started_at",
        "submittedAt": "submitted_at",
        "approvedAt": "approved_at",
        "score": "score",
        "attemptCount": "attempt_count",
        "updatedAt": "updated_at",
    }, "progress_id"),
    ("Attempts", "attempts", {
        "attemptId": "attempt_id",
        "progressId": "progress_id",
        "studentId": "student_id",
        "lessonId": "lesson_id",
        "attemptNumber": "attempt_number",
        "startedAt": "started_at",
        "deadlineAt": "deadline_at",
        "submittedAt": "submitted_at",
        "status": "status",
        "score": "score",
        "reviewerId": "reviewer_id",
        "reviewedAt": "reviewed_at",
        "reviewComments": "review_comments",
        "retryAuthorized": "retry_authorized",
        "createdAt": "created_at",
        "updatedAt": "updated_at",
    }, "attempt_id"),
    ("Answers", "answers", {
        "answerId": "answer_id",
        "attemptId": "attempt_id",
        "questionId": "question_id",
        "answerText": "answer_text",
        "selectedOptionId": "selected_option_id",
        "isCorrect": "is_correct",
        "awardedPoints": "awarded_points",
        "savedAt": "saved_at",
        "submittedAt": "submitted_at",
    }, "answer_id"),
    ("Files", "files", {
        "fileId": "file_id",
        "attemptId": "attempt_id",
        "studentId": "student_id",
        "lessonId": "lesson_id",
        "fileName": "file_name",
        "mimeType": "mime_type",
        "sizeBytes": "size_bytes",
        "driveFileId": "drive_file_id",
        "driveUrl": "drive_url",
        "uploadedAt": "uploaded_at",
        "status": "status",
    }, "file_id"),
    ("Reviews", "reviews", {
        "reviewId": "review_id",
        "attemptId": "attempt_id",
        "reviewerId": "reviewer_id",
        "decision": "decision",
        "score": "score",
        "comments": "comments",
        "correctionDeadline": "correction_deadline",
        "unlockNextLesson": "unlock_next_lesson",
        "reviewedAt": "reviewed_at",
    }, "review_id"),
    ("Certificates", "certificates", {
        "certificateId": "certificate_id",
        "studentId": "student_id",
        "courseId": "course_id",
        "certificateNumber": "certificate_number",
        "verificationCode": "verification_code",
        "issueDate": "issue_date",
        "finalScore": "final_score",
        "driveFileId": "drive_file_id",
        "driveUrl": "drive_url",
        "status": "status",
    }, "certificate_id"),
    ("AuditLog", "audit_log", {
        "logId": "log_id",
        "actorType": "actor_type",
        "actorId": "actor_id",
        "action": "action",
        "entityType": "entity_type",
        "entityId": "entity_id",
        "detailsJson": "details_json",
        "createdAt": "created_at",
    }, "log_id"),
    ("Settings", "settings", {
        "key": "key",
        "value": "value",
        "valueType": "value_type",
        "description": "description",
        "updatedAt": "updated_at",
    }, "key"),
    ("Lists", "lists", {
        "listName": "list_name",
        "value": "value",
        "labelPt": "label_pt",
        "sortOrder": "sort_order",
        "active": "active",
    }, "list_name,value"),
    ("MediaContent", "media_content", {
        "__rowId": "media_id",
        "mediaId": "media_id",
        "videoId": "media_id",
        "contentId": "media_id",
        "id": "media_id",
        "courseId": "course_id",
        "title": "title",
        "url": "url",
        "description": "description",
        "visibility": "visibility",
        "allowedEmails": "allowed_emails",
        "status": "status",
        "sortOrder": "sort_order",
        "createdAt": "created_at",
        "updatedAt": "updated_at",
    }, "media_id"),
    ("SchemaGuide", "schema_guide", {
        "sheetName": "sheet_name",
        "purpose": "purpose",
        "primaryKey": "primary_key",
        "notes": "notes",
    }, "sheet_name"),
]

BOOL_COLUMNS = {"active", "is_required", "is_correct", "retry_authorized", "unlock_next_lesson"}
JSON_COLUMNS = {"allowed_emails", "details_json"}
INTEGER_COLUMNS = {
    "attempt_count",
    "attempt_number",
    "lesson_number",
    "option_order",
    "question_order",
    "section_order",
    "size_bytes",
    "sort_order",
    "source_row",
}
NUMERIC_COLUMNS = {
    "awarded_points",
    "exercise_minutes",
    "final_score",
    "individual_minutes",
    "passing_score",
    "points",
    "progress_percent",
    "score",
    "theory_minutes",
    "total_hours",
}
TIMESTAMP_COLUMNS = {
    "approved_at",
    "completed_at",
    "correction_deadline",
    "created_at",
    "deadline_at",
    "end_date",
    "enrolled_at",
    "expires_at",
    "generated_at",
    "imported_at",
    "issue_date",
    "joined_at",
    "last_login_at",
    "reviewed_at",
    "revoked_at",
    "saved_at",
    "started_at",
    "start_date",
    "submitted_at",
    "unlocked_at",
    "updated_at",
    "uploaded_at",
}


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "sim", "y"}


def parse_integer(value: Any):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def parse_decimal(value: Any):
    try:
        return Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def parse_timestamp(value: Any):
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    if not text:
        return None

    try:
        serial = float(text)
        if serial > 1:
            base = datetime(1899, 12, 30, tzinfo=timezone.utc)
            return base + timedelta(days=serial)
    except ValueError:
        pass

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return text


def parse_json_value(column: str, value: Any):
    if column == "allowed_emails":
        if isinstance(value, list):
            return Jsonb(value)
        text = str(value).strip()
        if not text:
            return Jsonb([])
        if text.startswith("["):
            try:
                return Jsonb(json.loads(text))
            except json.JSONDecodeError:
                pass
        emails = [item.strip().lower() for item in text.replace(";", ",").split(",") if item.strip()]
        return Jsonb(emails)

    try:
        return Jsonb(json.loads(value))
    except Exception:
        return Jsonb({})


def parse_value(column: str, value: Any):
    if value in ("", None):
        return None
    if column in BOOL_COLUMNS:
        return parse_bool(value)
    if column in JSON_COLUMNS:
        return parse_json_value(column, value)
    if column in INTEGER_COLUMNS:
        return parse_integer(value)
    if column in NUMERIC_COLUMNS:
        return parse_decimal(value)
    if column in TIMESTAMP_COLUMNS:
        return parse_timestamp(value)
    return value


def excel_column_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref or "")
    if not match:
        return 0

    index = 0
    for char in match.group(1):
        index = index * 26 + (ord(char) - 64)
    return index - 1


def read_xlsx_values(path: str | Path) -> dict[str, list[list[Any]]]:
    workbook_path = Path(path)
    sheets: dict[str, list[list[Any]]] = {}

    with ZipFile(workbook_path) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("m:si", EXCEL_MAIN_NS):
                texts = [node.text or "" for node in item.findall(".//m:t", EXCEL_MAIN_NS)]
                shared_strings.append("".join(texts))

        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rels = {}
        for rel in rels_root.findall("pr:Relationship", EXCEL_PACKAGE_REL_NS):
            target = rel.attrib.get("Target", "")
            if not target.startswith("/"):
                target = "xl/" + target.lstrip("/")
            rels[rel.attrib["Id"]] = target

        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))

        def cell_value(cell):
            cell_type = cell.attrib.get("t")
            if cell_type == "s":
                value_node = cell.find("m:v", EXCEL_MAIN_NS)
                if value_node is None or value_node.text is None:
                    return ""
                return shared_strings[int(value_node.text)]
            if cell_type == "inlineStr":
                return "".join(node.text or "" for node in cell.findall(".//m:t", EXCEL_MAIN_NS))
            value_node = cell.find("m:v", EXCEL_MAIN_NS)
            return value_node.text if value_node is not None and value_node.text is not None else ""

        for sheet in workbook_root.findall(".//m:sheet", EXCEL_MAIN_NS):
            sheet_name = sheet.attrib["name"]
            relation_id = sheet.attrib.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            )
            target = rels.get(relation_id or "")
            if not target:
                sheets[sheet_name] = []
                continue

            sheet_root = ET.fromstring(archive.read(target))
            rows = []
            for row in sheet_root.findall(".//m:sheetData/m:row", EXCEL_MAIN_NS):
                values = []
                for cell in row.findall("m:c", EXCEL_MAIN_NS):
                    index = excel_column_index(cell.attrib.get("r", ""))
                    while len(values) <= index:
                        values.append("")
                    values[index] = cell_value(cell)
                rows.append(values)
            sheets[sheet_name] = rows

    return sheets


def rows_from_values(sheet_name: str, values: list[list[Any]]) -> list[dict[str, Any]]:
    if len(values) < 2:
        return []

    headers = [str(header).strip() for header in values[0]]
    rows = []
    for row_number, raw in enumerate(values[1:], start=2):
        row = {}
        for index, header in enumerate(headers):
            if not header:
                continue
            row[header] = raw[index] if index < len(raw) else ""
        if any(value not in ("", None) for value in row.values()):
            row["__rowNumber"] = row_number
            row["__rowId"] = hashlib.sha256(f"{sheet_name}:{row_number}".encode("utf-8")).hexdigest()
            rows.append(row)
    return rows


def read_xlsx_sheet(workbook_values: dict[str, list[list[Any]]], sheet_name: str) -> list[dict[str, Any]]:
    return rows_from_values(sheet_name, workbook_values.get(sheet_name, []))


def mapped_rows_for_sheet(raw_rows: list[dict[str, Any]], mapping: dict[str, str], key: str):
    mapped_rows = []
    skipped_missing_key = 0
    missing_key_examples = []
    seen_keys = set()
    duplicate_keys = set()

    for raw in raw_rows:
        mapped = {}
        for source, target in mapping.items():
            parsed = parse_value(target, raw.get(source))
            if parsed is not None or target not in mapped:
                mapped[target] = parsed

        key_values = tuple(mapped.get(part) for part in key.split(","))
        if not all(key_values):
            skipped_missing_key += 1
            if len(missing_key_examples) < 5:
                missing_key_examples.append(raw.get("__rowNumber"))
            continue

        if key_values in seen_keys:
            duplicate_keys.add("|".join(str(value) for value in key_values))
        seen_keys.add(key_values)
        mapped_rows.append(mapped)

    return mapped_rows, {
        "mappedRows": len(mapped_rows),
        "skippedMissingKey": skipped_missing_key,
        "missingKeyExampleRows": missing_key_examples,
        "duplicateKeys": sorted(duplicate_keys)[:10],
    }


def upsert_rows(conn, table: str, rows: list[dict[str, Any]], key: str):
    if not rows:
        return 0
    columns = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(columns))
    column_sql = ", ".join(columns)
    conflict_sql = ", ".join(key.split(","))
    update_columns = [column for column in columns if column not in key.split(",")]
    update_sql = ", ".join([f"{column}=excluded.{column}" for column in update_columns])
    conflict_action = f"do update set {update_sql}" if update_sql else "do nothing"
    sql = f"""
      insert into courseplatform.{table} ({column_sql})
      values ({placeholders})
      on conflict ({conflict_sql}) {conflict_action}
    """
    values = [tuple(row.get(column) for column in columns) for row in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, values)
    return len(rows)


def migrate_from_reader(read_rows, database_url: str, dry_run: bool, validate_only: bool):
    report = {}
    if not validate_only and psycopg is None:
        raise SystemExit("Missing psycopg. Install dependencies with: pip install -r requirements.txt")
    conn = None if validate_only else psycopg.connect(database_url, connect_timeout=15)
    try:
        for sheet_name, table_name, mapping, key in TABLES:
            raw_rows = read_rows(sheet_name)
            mapped_rows, sheet_report = mapped_rows_for_sheet(raw_rows, mapping, key)
            report[sheet_name] = {
                "table": table_name,
                "rawRows": len(raw_rows),
                **sheet_report,
            }
            if conn:
                upsert_rows(conn, table_name, mapped_rows, key)
        if conn:
            if dry_run:
                conn.rollback()
            else:
                conn.commit()
    finally:
        if conn:
            conn.close()
    return report


def migrate_from_xlsx(xlsx_path: str, database_url: str | None, dry_run: bool, validate_only: bool):
    workbook_values = read_xlsx_values(xlsx_path)
    return migrate_from_reader(
        lambda sheet_name: read_xlsx_sheet(workbook_values, sheet_name),
        database_url or "",
        dry_run,
        validate_only,
    )


def main():
    if load_dotenv is not None:
        load_dotenv()

    parser = argparse.ArgumentParser(description="Migrate CoursePlatform XLSX export data to Supabase/Postgres.")
    parser.add_argument("--xlsx", default=os.getenv("COURSEPLATFORM_XLSX"), required=False)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), required=False)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    if not args.xlsx:
        raise SystemExit("Missing --xlsx or COURSEPLATFORM_XLSX.")
    if not args.validate_only and not args.database_url:
        raise SystemExit("Missing --database-url or DATABASE_URL. Use --validate-only to inspect the XLSX without Supabase.")

    started = datetime.now(timezone.utc)
    report = migrate_from_xlsx(args.xlsx, args.database_url, args.dry_run, args.validate_only)
    print(json.dumps({
        "startedAt": started.isoformat(),
        "source": "xlsx",
        "dryRun": args.dry_run,
        "validateOnly": args.validate_only,
        "sheets": report,
    }, indent=2))


if __name__ == "__main__":
    main()
