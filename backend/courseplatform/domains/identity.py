import secrets
from collections.abc import Callable
from typing import Any

from ..contracts import str_value


ACTION_BINDINGS = (
    ("login", "login"),
    ("recoverStudentAccess", "recover_student_access"),
    ("completeStudentPasswordReset", "complete_student_password_reset"),
    ("logout", "logout"),
    ("adminLogin", "admin_login"),
    ("recoverAdminAccess", "recover_admin_access"),
    ("adminLogout", "logout"),
    ("adminMe", "admin_me"),
    ("updateMyProfile", "update_my_profile"),
    ("changeMyAccessCode", "change_my_access_code"),
    ("changeMyEmail", "change_my_email"),
)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def public_student_id() -> str:
    return f"STU-{secrets.randbelow(100000):05d}"


def valid_password(value: str) -> bool:
    return len(str_value(value)) >= 8


def serialize_student(
    row: dict[str, Any] | None,
    *,
    as_boolean: Callable[[Any], bool],
    as_iso: Callable[[Any], str | None],
    telegram_recipient: Callable[[Any], str],
    preferences: Callable[[dict[str, Any] | None], dict[str, bool]],
):
    if not row:
        return None
    return {
        "studentId": row["student_id"],
        "publicStudentId": row.get("public_student_id") or "",
        "fullName": row.get("full_name"),
        "email": row.get("email"),
        "status": row.get("status"),
        "country": row.get("country"),
        "organization": row.get("organization"),
        "phone": row.get("phone"),
        "jobTitle": row.get("job_title"),
        "interests": row.get("interests"),
        "profilePhotoUrl": row.get("profile_photo_url"),
        "whatsappOptIn": as_boolean(row.get("whatsapp_opt_in")),
        "whatsappOptInAt": as_iso(row.get("whatsapp_opt_in_at")),
        "emailOptIn": as_boolean(row.get("email_opt_in")),
        "emailOptInAt": as_iso(row.get("email_opt_in_at")),
        "telegramLinked": bool(telegram_recipient(row.get("telegram_chat_id"))),
        "telegramOptIn": as_boolean(row.get("telegram_opt_in")),
        "telegramOptInAt": as_iso(row.get("telegram_opt_in_at")),
        "pushSubscriptionCount": int(row.get("push_subscription_count") or 0),
        "notificationPreferences": preferences(row),
        "createdAt": as_iso(row.get("created_at")),
        "updatedAt": as_iso(row.get("updated_at")),
        "lastLoginAt": as_iso(row.get("last_login_at")),
    }


def serialize_admin(row: dict[str, Any] | None, *, as_iso: Callable[[Any], str | None]):
    if not row:
        return None
    return {
        "adminId": row["admin_id"],
        "fullName": row.get("full_name"),
        "email": row.get("email"),
        "role": row.get("role"),
        "status": row.get("status"),
        "createdAt": as_iso(row.get("created_at")),
        "updatedAt": as_iso(row.get("updated_at")),
    }
