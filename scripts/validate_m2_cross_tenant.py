"""Validate M2 tenant boundaries against a deployed API and the linked database.

The script creates synthetic organization-B records, never prints tokens or
personal data, and removes every fixture in a ``finally`` block.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.courseplatform import actions
from backend.courseplatform.config import get_settings
from backend.courseplatform.db import connection


ORG_A = "ORG-LMTWEBNAIRS"
ORG_B = "ORG-M2-VALIDATION"
STUDENT_B = "STU-M2-VALIDATION"
ADMIN_B = "ADM-M2-VALIDATION"
COURSE_B = "COURSE-M2-VALIDATION"
ROOM_B = "ROOM-M2-VALIDATION"
NOTIFICATION_B = "NTF-M2-VALIDATION"
DELIVERY_B = "NDL-M2-VALIDATION"
MARKER = "m2-validation"
TEMP_SESSION_HASH = ""


class ValidationError(RuntimeError):
    pass


def temporary_admin_token() -> str:
    """Create an isolated session for an existing owner/admin in organization A."""
    global TEMP_SESSION_HASH
    with connection() as conn:
        admin = conn.execute(
            """
            select membership.admin_id
            from courseplatform.organization_memberships membership
            join courseplatform.admins admin on admin.admin_id = membership.admin_id
            where membership.organization_id = %s
              and membership.membership_role in ('OWNER', 'ADMIN')
              and membership.status = 'ACTIVE'
              and admin.status = 'ACTIVE'
            order by case membership.membership_role when 'OWNER' then 0 else 1 end,
                     membership.created_at
            limit 1
            """,
            (ORG_A,),
        ).fetchone()
        if not admin:
            raise ValidationError("Nenhum proprietário/administrador ativo disponível na instituição A.")
        session = actions.create_session(
            conn,
            f"ADMIN:{admin['admin_id']}",
            user_agent="courseplatform-m2-validation/1.0",
            organization_id=ORG_A,
        )
        conn.commit()
    TEMP_SESSION_HASH = actions.hash_secret(session["token"])
    return session["token"]


def base_url() -> str:
    value = (
        os.getenv("COURSEPLATFORM_VALIDATION_BASE_URL", "").strip()
        or os.getenv("PLATFORM_URL", "").strip()
    ).rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValidationError("A validação remota exige uma origem HTTPS válida.")
    return value


def api_action(origin: str, token: str, action: str, **payload) -> dict:
    body = json.dumps({"action": action, "adminToken": token, **payload}).encode("utf-8")
    request = urllib.request.Request(
        f"{origin}/api",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "courseplatform-m2-validation/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read(8192)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as parse_error:
            raise ValidationError(f"{action}: HTTP {error.code} sem JSON válido.") from parse_error


def assert_success(result: dict, action: str) -> dict:
    if result.get("success") is not True:
        code = ((result.get("error") or {}).get("code") or "UNKNOWN")
        raise ValidationError(f"{action}: falhou com {code}.")
    return result.get("data") or {}


def assert_error(result: dict, action: str, expected: str) -> None:
    code = ((result.get("error") or {}).get("code") or "")
    if result.get("success") is not False or code != expected:
        raise ValidationError(f"{action}: esperado {expected}; recebido {code or 'SUCCESS'}.")
    print(f"{action}: denied={expected}")


def contains_identifier(value, identifier: str) -> bool:
    if isinstance(value, dict):
        return any(contains_identifier(item, identifier) for item in value.values())
    if isinstance(value, list):
        return any(contains_identifier(item, identifier) for item in value)
    return value == identifier


def cleanup() -> None:
    global TEMP_SESSION_HASH
    with connection() as conn:
        if TEMP_SESSION_HASH:
            conn.execute(
                "delete from courseplatform.sessions where session_token = %s",
                (TEMP_SESSION_HASH,),
            )
        conn.execute("delete from courseplatform.notification_deliveries where delivery_id = %s", (DELIVERY_B,))
        conn.execute("delete from courseplatform.notifications where notification_id = %s", (NOTIFICATION_B,))
        conn.execute("delete from courseplatform.chat_rooms where room_id = %s", (ROOM_B,))
        conn.execute("delete from courseplatform.certificate_settings where course_id = %s", (COURSE_B,))
        conn.execute("delete from courseplatform.courses where course_id = %s", (COURSE_B,))
        conn.execute(
            "delete from courseplatform.organization_memberships where organization_id = %s or student_id = %s or admin_id = %s",
            (ORG_B, STUDENT_B, ADMIN_B),
        )
        conn.execute("delete from courseplatform.admins where admin_id = %s", (ADMIN_B,))
        conn.execute("delete from courseplatform.students where student_id = %s", (STUDENT_B,))
        conn.execute("delete from courseplatform.organizations where organization_id = %s", (ORG_B,))
        conn.commit()
    TEMP_SESSION_HASH = ""


def seed() -> None:
    cleanup()
    with connection() as conn:
        conn.execute(
            """
            insert into courseplatform.organizations
              (organization_id, slug, display_name, legal_name, status, settings_json)
            values (%s, %s, %s, %s, 'ACTIVE', '{}'::jsonb)
            """,
            (ORG_B, MARKER, "M2 Validation", "M2 Validation"),
        )
        conn.execute(
            """
            insert into courseplatform.students
              (student_id, public_student_id, full_name, email, status, created_at, updated_at)
            values (%s, %s, %s, %s, 'ACTIVE', now(), now())
            """,
            (STUDENT_B, "M2VAL0001", "M2 Validation Student", "student@m2-validation.invalid"),
        )
        conn.execute(
            """
            insert into courseplatform.admins
              (admin_id, student_id, full_name, email, role, status, created_at, updated_at)
            values (%s, %s, %s, %s, 'REVIEWER', 'ACTIVE', now(), now())
            """,
            (ADMIN_B, STUDENT_B, "M2 Validation Reviewer", "reviewer@m2-validation.invalid"),
        )
        conn.execute(
            "delete from courseplatform.organization_memberships where organization_id = %s and (student_id = %s or admin_id = %s)",
            (ORG_A, STUDENT_B, ADMIN_B),
        )
        conn.execute(
            """
            insert into courseplatform.organization_memberships
              (membership_id, organization_id, student_id, membership_role, status)
            values ('MEM-M2-STUDENT', %s, %s, 'STUDENT', 'ACTIVE')
            """,
            (ORG_B, STUDENT_B),
        )
        conn.execute(
            """
            insert into courseplatform.organization_memberships
              (membership_id, organization_id, admin_id, membership_role, status)
            values ('MEM-M2-REVIEWER', %s, %s, 'REVIEWER', 'ACTIVE')
            """,
            (ORG_B, ADMIN_B),
        )
        conn.execute(
            """
            insert into courseplatform.courses
              (course_id, course_code, title, description, status, organization_id, created_at, updated_at)
            values (%s, 'M2VAL', 'M2 Validation Course', %s, 'ACTIVE', %s, now(), now())
            """,
            (COURSE_B, MARKER, ORG_B),
        )
        conn.execute(
            """
            insert into courseplatform.chat_rooms
              (room_id, organization_id, room_key, room_type, name, description, status)
            values (%s, %s, %s, 'COMMUNITY', 'M2 Validation Room', %s, 'ACTIVE')
            """,
            (ROOM_B, ORG_B, MARKER, MARKER),
        )
        conn.execute(
            """
            insert into courseplatform.notifications
              (notification_id, organization_id, student_id, category, title, message, priority)
            values (%s, %s, %s, 'GENERAL', %s, %s, 'NORMAL')
            """,
            (NOTIFICATION_B, ORG_B, STUDENT_B, MARKER, MARKER),
        )
        conn.execute(
            """
            insert into courseplatform.notification_deliveries
              (delivery_id, notification_id, channel, recipient, status, attempt_count, updated_at)
            values (%s, %s, 'EMAIL', 'student@m2-validation.invalid', 'FAILED', 0, now())
            """,
            (DELIVERY_B, NOTIFICATION_B),
        )
        conn.commit()


def validate(origin: str, token: str) -> None:
    local_statistics = actions.admin_platform_statistics({"adminToken": token})
    assert_success(local_statistics, "local_admin_platform_statistics")
    print("local_admin_platform_statistics: ok")
    assert_error(
        api_action(
            origin,
            token,
            "adminSaveCertificateSurvey",
            courseId=COURSE_B,
            congratulationsMessage="Validation",
            surveyQuestions=[],
        ),
        "survey_cross_tenant_write",
        "COURSE_NOT_FOUND",
    )
    surveys = assert_success(
        api_action(origin, token, "adminListCertificateSurveys", query=MARKER, limit=10),
        "survey_cross_tenant_list",
    )
    if contains_identifier(surveys, COURSE_B):
        raise ValidationError("survey_cross_tenant_list: curso B ficou visível para A.")
    print("survey_cross_tenant_list: isolated=ok")

    notifications = assert_success(
        api_action(origin, token, "adminListNotifications", query=MARKER, limit=10),
        "notification_cross_tenant_list",
    )
    if contains_identifier(notifications, NOTIFICATION_B):
        raise ValidationError("notification_cross_tenant_list: notificação B ficou visível para A.")
    print("notification_cross_tenant_list: isolated=ok")
    assert_error(
        api_action(
            origin,
            token,
            "adminCreateNotification",
            studentIds=[STUDENT_B],
            title="Validation",
            message="Validation",
        ),
        "notification_cross_tenant_write",
        "NOTIFICATION_RECIPIENT_REQUIRED",
    )

    rooms = assert_success(api_action(origin, token, "adminListChatRooms"), "chat_cross_tenant_list")
    if contains_identifier(rooms, ROOM_B):
        raise ValidationError("chat_cross_tenant_list: sala B ficou visível para A.")
    print("chat_cross_tenant_list: isolated=ok")
    assert_error(
        api_action(origin, token, "adminGetChatMessages", roomId=ROOM_B),
        "chat_cross_tenant_read",
        "CHAT_ROOM_NOT_FOUND",
    )

    local_students = actions.admin_list_students({
        "adminToken": token,
        "query": MARKER,
        "limit": 10,
    })
    assert_success(local_students, "local_student_cross_tenant_list")
    print("local_student_cross_tenant_list: ok")
    local_staff = actions.admin_list_staff({
        "adminToken": token,
        "query": MARKER,
        "limit": 10,
    })
    assert_success(local_staff, "local_staff_cross_tenant_list")
    print("local_staff_cross_tenant_list: ok")
    claimed = actions.claim_notification_deliveries("EMAIL", [NOTIFICATION_B], 1, ORG_A)
    if claimed:
        raise ValidationError("delivery_cross_tenant_claim: A reclamou uma entrega de B.")
    with connection() as conn:
        row = conn.execute(
            "select status, attempt_count from courseplatform.notification_deliveries where delivery_id = %s",
            (DELIVERY_B,),
        ).fetchone() or {}
    if row.get("status") != "FAILED" or int(row.get("attempt_count") or 0) != 0:
        raise ValidationError("delivery_cross_tenant_claim: a entrega de B foi alterada.")
    print("delivery_cross_tenant_claim: isolated=ok")

    staff = assert_success(
        api_action(origin, token, "adminListStaff", query=MARKER, limit=10),
        "staff_cross_tenant_list",
    )
    if contains_identifier(staff, ADMIN_B):
        raise ValidationError("staff_cross_tenant_list: staff B ficou visível para A.")
    print("staff_cross_tenant_list: isolated=ok")

    students = assert_success(
        api_action(origin, token, "adminListStudents", query=MARKER, limit=10),
        "student_cross_tenant_list",
    )
    if contains_identifier(students, STUDENT_B):
        raise ValidationError("student_cross_tenant_list: estudante B ficou visível para A.")
    print("student_cross_tenant_list: isolated=ok")
    assert_error(
        api_action(origin, token, "adminGetStudentDetails", studentId=STUDENT_B),
        "student_cross_tenant_read",
        "STUDENT_NOT_FOUND",
    )

    assert_success(
        api_action(origin, token, "adminGetPlatformStatistics"),
        "admin_platform_statistics",
    )
    print("admin_platform_statistics: ok")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        parser.error("A validação cria fixtures temporárias; confirme com --apply.")
    get_settings().require_database()
    origin = base_url()
    seed()
    try:
        token = os.getenv("COURSEPLATFORM_VALIDATION_ADMIN_TOKEN", "").strip()
        if not token:
            token = temporary_admin_token()
        validate(origin, token)
    finally:
        cleanup()
    print("m2_cross_tenant_validation=passed cleanup=passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as error:
        print(f"m2_cross_tenant_validation=failed reason={error}", file=sys.stderr)
        raise SystemExit(1)
