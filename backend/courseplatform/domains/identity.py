import hashlib
import hmac
import json
import logging
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from ..contracts import ApiError, str_value


logger = logging.getLogger(__name__)


ACTION_BINDINGS = (
    ("login", "login"),
    ("registerStudentAccount", "register_student_account"),
    ("completeStudentAccountVerification", "complete_student_account_verification"),
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


PASSWORD_RESET_GENERIC_MESSAGE = (
    "Se existir uma conta ativa associada a esse email, receberá uma mensagem "
    "com as instruções para definir uma nova palavra-passe."
)

REGISTRATION_GENERIC_MESSAGE = (
    "Se o email puder ser utilizado para uma nova conta, receberá uma mensagem "
    "para confirmar o cadastro e ativar o acesso."
)

ACCOUNT_VERIFICATION_DELIVERY_FAILED_MESSAGE = (
    "A conta foi registada, mas não foi possível enviar o email de confirmação. "
    "Tente novamente dentro de alguns minutos."
)


@dataclass(frozen=True)
class IdentityRuntime:
    require_fields: Callable[..., Any]
    fetch_one: Callable[..., Any]
    database_api_error: Callable[..., Any]
    verify_password: Callable[..., Any]
    connection: Callable[..., Any]
    revoke_sessions: Callable[..., Any]
    create_session: Callable[..., Any]
    public_student: Callable[..., Any]
    public_admin: Callable[..., Any]
    iso: Callable[..., Any]
    success: Callable[..., Any]
    get_settings: Callable[..., Any]
    utc_now: Callable[..., Any]
    generate_id: Callable[..., Any]
    hash_secret: Callable[..., Any]
    audit: Callable[..., Any]
    parse_datetime: Callable[..., Any]
    create_student_notification: Callable[..., Any]
    configured_admin_recovery_hashes: Callable[..., Any]
    verify_admin_recovery_key: Callable[..., Any]
    generate_access_code: Callable[..., Any]
    mask_email: Callable[..., Any]
    prepare_chat_feature_schema: Callable[..., Any]
    admin_context: Callable[..., Any]
    student_context: Callable[..., Any]
    prepare_notification_feature_schema: Callable[..., Any]
    as_bool: Callable[..., Any]
    normalize_whatsapp_recipient: Callable[..., Any]
    normalize_email_recipient: Callable[..., Any]
    normalize_telegram_recipient: Callable[..., Any]
    notification_preferences: Callable[..., Any]
    default_notification_preferences: dict[str, bool]
    student_notification_channel_info: Callable[..., Any]
    validated_email_change: Callable[..., Any]
    student_context_with_conn: Callable[..., Any]
    verify_password_with_conn: Callable[..., Any]
    secure_student_email_update: Callable[..., Any]


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
        "emailVerified": bool(row.get("email_verified_at")),
        "emailVerifiedAt": as_iso(row.get("email_verified_at")),
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
    student_id = row.get("identity_student_id") or row.get("student_id")
    identity_status = row.get("identity_status") or ("" if student_id else None)
    return {
        "adminId": row["admin_id"],
        "studentId": student_id or "",
        "fullName": row.get("full_name"),
        "email": row.get("identity_email") or row.get("email"),
        "role": row.get("role"),
        "status": row.get("status"),
        "identitySource": "STUDENT" if student_id else "LEGACY_ADMIN",
        "identityStatus": identity_status,
        "accessActive": bool(
            row.get("status") == "ACTIVE"
            and (not student_id or identity_status == "ACTIVE")
        ),
        "reviewScopes": row.get("reviewer_scopes") or [],
        "createdAt": as_iso(row.get("created_at")),
        "updatedAt": as_iso(row.get("updated_at")),
    }


def mask_email(email: str) -> str:
    local, separator, domain = (email or "").partition("@")
    if not separator:
        return email
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'*' * max(2, len(local) - len(visible))}@{domain}"


def password_reset_private_digest(kind: str, value: str, settings: Any) -> str:
    key = settings.password_reset_hash_key.encode("utf-8")
    if len(key) < 32:
        raise RuntimeError("PASSWORD_RESET_HASH_KEY is not configured securely.")
    return hmac.new(key, f"{kind}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def password_reset_public_result(success: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    return success({"message": PASSWORD_RESET_GENERIC_MESSAGE})


def registration_public_result(success: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    return success({"message": REGISTRATION_GENERIC_MESSAGE})


def link_matching_legacy_staff(conn: Any, student_id: str, email: str) -> str:
    linked_admin = conn.execute(
        """
        update courseplatform.admins a
        set student_id = %s, email = %s, updated_at = now()
        where a.student_id is null
          and a.status = 'ACTIVE'
          and lower(btrim(a.email)) = lower(btrim(%s))
          and not exists (
            select 1
            from courseplatform.admins assigned
            where assigned.student_id = %s
          )
        returning a.admin_id
        """,
        (student_id, email, email, student_id),
    ).fetchone()
    conn.execute(
        """
        update courseplatform.sessions ses
        set active = false, revoked_at = now()
        where ses.active = true
          and ses.subject_id in (
            select 'ADMIN:' || a.admin_id
            from courseplatform.admins a
            where a.student_id = %s
          )
        """,
        (student_id,),
    )
    return str_value((linked_admin or {}).get("admin_id"))


def valid_registration_email(value: str) -> bool:
    return bool(
        value
        and len(value) <= 320
        and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value)
    )


def register_student_account_action(payload: dict[str, Any], runtime: IdentityRuntime):
    runtime.require_fields(payload, ["fullName", "email", "password", "confirmPassword"])
    full_name = str_value(payload.get("fullName"))
    email = normalize_email(payload.get("email"))
    password = str(payload.get("password") or "")
    confirmation = str(payload.get("confirmPassword") or "")
    country = str_value(payload.get("country"))
    organization = str_value(payload.get("organization"))
    if not 2 <= len(full_name) <= 160:
        raise ApiError("INVALID_FULL_NAME", "Indique o nome completo com 2 a 160 caracteres.")
    if not valid_registration_email(email):
        raise ApiError("INVALID_EMAIL", "Indique um endereço de email válido.")
    if password != confirmation:
        raise ApiError("PASSWORD_CONFIRMATION_MISMATCH", "A confirmação da palavra-passe não corresponde.")
    if not valid_password(password) or len(password) > 128:
        raise ApiError("INVALID_NEW_PASSWORD", "A palavra-passe deve ter entre 8 e 128 caracteres.")
    if len(country) > 100 or len(organization) > 160:
        raise ApiError("REGISTRATION_DETAILS_TOO_LONG", "Os dados do cadastro excedem o tamanho permitido.")

    settings = runtime.get_settings()
    if len(settings.password_reset_hash_key.encode("utf-8")) < 32:
        logger.error("Account registration is unavailable because PASSWORD_RESET_HASH_KEY is missing or too short.")
        raise ApiError("REGISTRATION_UNAVAILABLE", "O cadastro não está disponível neste momento.")

    source = str_value(payload.get("_requestSource"))[:256] or "unknown"
    email_hash = password_reset_private_digest("registration-email", email, settings)
    source_hash = password_reset_private_digest("registration-source", source, settings)
    token = secrets.token_urlsafe(48)
    token_hash = runtime.hash_secret(token)
    verification_id = runtime.generate_id("VFY")
    expires_at = runtime.utc_now() + timedelta(minutes=max(10, settings.account_verification_ttl_minutes))
    delivery = None

    try:
        with runtime.connection() as conn:
            for lock_key in sorted({email_hash, source_hash}):
                conn.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
            source_count = conn.execute(
                """
                select count(*) as count
                from courseplatform.student_account_verifications
                where source_hash = %s
                  and created_at >= now() - make_interval(mins => %s)
                """,
                (source_hash, max(1, settings.registration_source_window_minutes)),
            ).fetchone()
            email_count = conn.execute(
                """
                select count(*) as count
                from courseplatform.student_account_verifications
                where email_hash = %s
                  and created_at >= now() - make_interval(mins => %s)
                """,
                (email_hash, max(1, settings.registration_account_window_minutes)),
            ).fetchone()
            limited = (
                int((source_count or {}).get("count") or 0) >= max(1, settings.registration_source_limit)
                or int((email_count or {}).get("count") or 0) >= max(1, settings.registration_account_limit)
            )
            student = conn.execute(
                "select * from courseplatform.students where email = %s for update",
                (email,),
            ).fetchone()
            if not limited and student and not (
                student.get("status") == "PENDING_VERIFICATION"
                and not student.get("email_verified_at")
            ):
                raise ApiError(
                    "EMAIL_ALREADY_REGISTERED",
                    "Este email já está cadastrado. Inicie sessão ou recupere a palavra-passe.",
                )
            can_register = not limited and (
                not student
                or (
                    student.get("status") == "PENDING_VERIFICATION"
                    and not student.get("email_verified_at")
                )
            )
            if can_register:
                if student:
                    student = conn.execute(
                        """
                        update courseplatform.students
                        set full_name = %s,
                            password_hash = crypt(%s, gen_salt('bf', 12)),
                            password_changed_at = now(), password_reset_required = false,
                            country = %s, organization = %s, updated_at = now()
                        where student_id = %s
                        returning *
                        """,
                        (full_name, password, country or None, organization or None, student["student_id"]),
                    ).fetchone()
                else:
                    for _ in range(12):
                        student_id = runtime.generate_id("STU")
                        student = conn.execute(
                            """
                            insert into courseplatform.students
                              (student_id, public_student_id, full_name, email, access_code, password_hash,
                               password_changed_at, password_reset_required, status, country, organization,
                               email_verified_at, created_at, updated_at)
                            values (%s, %s, %s, %s, null, crypt(%s, gen_salt('bf', 12)),
                                    now(), false, 'PENDING_VERIFICATION', %s, %s, null, now(), now())
                            on conflict do nothing
                            returning *
                            """,
                            (
                                student_id,
                                public_student_id(),
                                full_name,
                                email,
                                password,
                                country or None,
                                organization or None,
                            ),
                        ).fetchone()
                        if student:
                            break
                        student = conn.execute(
                            "select * from courseplatform.students where email = %s for update",
                            (email,),
                        ).fetchone()
                        if student:
                            break
                if student and student.get("status") == "PENDING_VERIFICATION" and not student.get("email_verified_at"):
                    conn.execute(
                        """
                        update courseplatform.student_account_verifications
                        set status = 'INVALIDATED', invalidated_at = now()
                        where student_id = %s and consumed_at is null and invalidated_at is null
                        """,
                        (student["student_id"],),
                    )
                    conn.execute(
                        """
                        insert into courseplatform.student_account_verifications
                          (verification_id, student_id, email_hash, source_hash, token_hash,
                           status, expires_at, created_at)
                        values (%s, %s, %s, %s, %s, 'PENDING', %s, now())
                        """,
                        (
                            verification_id,
                            student["student_id"],
                            email_hash,
                            source_hash,
                            token_hash,
                            expires_at,
                        ),
                    )
                    runtime.audit(
                        conn,
                        "SYSTEM",
                        student["student_id"],
                        "STUDENT_ACCOUNT_REGISTRATION_REQUESTED",
                        "STUDENT",
                        student["student_id"],
                        {"verificationId": verification_id, "expiresAt": runtime.iso(expires_at)},
                    )
                    delivery = {"verificationId": verification_id, "token": token}
            conn.commit()
    except ApiError:
        raise
    except Exception as error:
        raise runtime.database_api_error(error) from error

    result = registration_public_result(runtime.success)
    if delivery:
        result["_accountVerificationDelivery"] = delivery
    return result


def complete_student_account_verification_action(payload: dict[str, Any], runtime: IdentityRuntime):
    runtime.require_fields(payload, ["token"])
    token = str_value(payload.get("token"))
    if not token or len(token) > 256:
        raise ApiError("ACCOUNT_VERIFICATION_TOKEN_INVALID", "O link de confirmação é inválido ou já expirou.")
    token_hash = runtime.hash_secret(token)
    verification_error = None
    student = None
    try:
        with runtime.connection() as conn:
            verification = conn.execute(
                """
                select v.*, s.status as student_status, s.email_verified_at
                from courseplatform.student_account_verifications v
                join courseplatform.students s on s.student_id = v.student_id
                where v.token_hash = %s
                for update of v, s
                """,
                (token_hash,),
            ).fetchone()
            expires_at = runtime.parse_datetime(verification.get("expires_at")) if verification else None
            valid_verification = bool(
                verification
                and verification.get("status") in {"PENDING", "DELIVERED"}
                and not verification.get("consumed_at")
                and not verification.get("invalidated_at")
                and expires_at
                and expires_at > runtime.utc_now()
                and verification.get("student_status") == "PENDING_VERIFICATION"
                and not verification.get("email_verified_at")
            )
            if not valid_verification:
                if verification and expires_at and expires_at <= runtime.utc_now():
                    conn.execute(
                        """
                        update courseplatform.student_account_verifications
                        set status = 'EXPIRED', invalidated_at = coalesce(invalidated_at, now())
                        where verification_id = %s
                        """,
                        (verification["verification_id"],),
                    )
                verification_error = ApiError(
                    "ACCOUNT_VERIFICATION_TOKEN_INVALID",
                    "O link de confirmação é inválido ou já expirou.",
                )
            else:
                student = conn.execute(
                    """
                    update courseplatform.students
                    set status = 'ACTIVE', email_verified_at = now(), updated_at = now()
                    where student_id = %s
                    returning *
                    """,
                    (verification["student_id"],),
                ).fetchone()
                linked_admin_id = link_matching_legacy_staff(
                    conn,
                    verification["student_id"],
                    student.get("email") if student else "",
                )
                if linked_admin_id:
                    runtime.audit(
                        conn,
                        "SYSTEM",
                        verification["student_id"],
                        "STAFF_IDENTITY_LINKED",
                        "ADMIN",
                        linked_admin_id,
                        {"studentId": verification["student_id"]},
                    )
                conn.execute(
                    """
                    update courseplatform.student_account_verifications
                    set status = 'CONSUMED', consumed_at = now()
                    where verification_id = %s
                    """,
                    (verification["verification_id"],),
                )
                conn.execute(
                    """
                    update courseplatform.student_account_verifications
                    set status = 'INVALIDATED', invalidated_at = now()
                    where student_id = %s and verification_id <> %s
                      and consumed_at is null and invalidated_at is null
                    """,
                    (verification["student_id"], verification["verification_id"]),
                )
                runtime.audit(
                    conn,
                    "STUDENT",
                    verification["student_id"],
                    "STUDENT_ACCOUNT_ACTIVATED",
                    "STUDENT",
                    verification["student_id"],
                    {"verificationId": verification["verification_id"]},
                )
            conn.commit()
    except Exception as error:
        if isinstance(error, ApiError):
            raise
        raise runtime.database_api_error(error) from error
    if verification_error:
        raise verification_error
    return runtime.success({"accountActivated": True, "student": runtime.public_student(student)})


def login_action(payload: dict[str, Any], runtime: IdentityRuntime):
    runtime.require_fields(payload, ["email", "accessCode"])
    email = normalize_email(payload["email"])
    try:
        student = runtime.fetch_one(
            "select * from courseplatform.students where email = %s",
            (email,),
        )
    except Exception as error:
        raise runtime.database_api_error(error) from error
    if not student or student.get("status") != "ACTIVE":
        total = runtime.fetch_one("select count(*) as total from courseplatform.students")
        if int(total.get("total") or 0) == 0:
            raise ApiError(
                "DATABASE_EMPTY",
                "A base de dados ligada ainda não tem estudantes. Confirme se o POSTGRES_URL aponta para a base migrada.",
            )
        raise ApiError("INVALID_CREDENTIALS", "Email ou palavra-passe inválidos.")
    try:
        if not runtime.verify_password(payload["accessCode"], student.get("password_hash")):
            raise ApiError("INVALID_CREDENTIALS", "Email ou palavra-passe inválidos.")
        with runtime.connection() as conn:
            runtime.revoke_sessions(conn, student["student_id"])
            session = runtime.create_session(
                conn,
                student["student_id"],
                payload.get("userAgent", ""),
                payload.get("ipHash", ""),
            )
            conn.execute(
                "update courseplatform.students set last_login_at = now(), updated_at = now() where student_id = %s",
                (student["student_id"],),
            )
            conn.commit()
    except ApiError:
        raise
    except Exception as error:
        raise runtime.database_api_error(error) from error
    return runtime.success({
        "sessionToken": session["token"],
        "expiresAt": runtime.iso(session["expiresAt"]),
        "student": runtime.public_student(student),
    })


def recover_student_access_action(payload: dict[str, Any], runtime: IdentityRuntime):
    runtime.require_fields(payload, ["email"])
    email = normalize_email(payload["email"])
    settings = runtime.get_settings()
    if len(settings.password_reset_hash_key.encode("utf-8")) < 32:
        logger.error(
            "Student password recovery is unavailable because PASSWORD_RESET_HASH_KEY is missing or too short."
        )
        return password_reset_public_result(runtime.success)

    source = str_value(payload.get("_requestSource"))[:256] or "unknown"
    email_hash = password_reset_private_digest("email", email, settings)
    source_hash = password_reset_private_digest("source", source, settings)
    token = secrets.token_urlsafe(48)
    reset_id = runtime.generate_id("PWR")
    expires_at = runtime.utc_now() + timedelta(minutes=max(5, settings.password_reset_ttl_minutes))
    delivery = None
    try:
        with runtime.connection() as conn:
            for lock_key in sorted({email_hash, source_hash}):
                conn.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
            source_count = conn.execute(
                """
                select count(*) as count
                from courseplatform.student_password_resets
                where source_hash = %s
                  and created_at >= now() - (%s * interval '1 minute')
                """,
                (source_hash, max(1, settings.password_reset_source_window_minutes)),
            ).fetchone() or {}
            email_count = conn.execute(
                """
                select count(*) as count
                from courseplatform.student_password_resets
                where email_hash = %s
                  and created_at >= now() - (%s * interval '1 minute')
                """,
                (email_hash, max(1, settings.password_reset_account_window_minutes)),
            ).fetchone() or {}
            throttled = (
                int(source_count.get("count") or 0) >= max(1, settings.password_reset_source_limit)
                or int(email_count.get("count") or 0) >= max(1, settings.password_reset_account_limit)
            )
            student = None if throttled else conn.execute(
                """
                select student_id, full_name, email, status
                from courseplatform.students
                where email = %s
                """,
                (email,),
            ).fetchone()
            if not throttled and not student:
                legacy_admin = conn.execute(
                    """
                    select admin_id, full_name, email
                    from courseplatform.admins
                    where lower(btrim(email)) = %s
                      and status = 'ACTIVE'
                      and student_id is null
                    for update
                    """,
                    (email,),
                ).fetchone()
                if legacy_admin:
                    for _ in range(12):
                        student = conn.execute(
                            """
                            insert into courseplatform.students
                              (student_id, public_student_id, full_name, email, access_code,
                               password_hash, password_changed_at, password_reset_required,
                               status, email_verified_at, created_at, updated_at)
                            values (%s, %s, %s, %s, null, null, null, true,
                                    'PENDING_VERIFICATION', null, now(), now())
                            on conflict do nothing
                            returning student_id, full_name, email, status
                            """,
                            (
                                runtime.generate_id("STU"),
                                public_student_id(),
                                legacy_admin.get("full_name") or "Utilizador",
                                email,
                            ),
                        ).fetchone()
                        if student:
                            break
                        student = conn.execute(
                            """
                            select student_id, full_name, email, status
                            from courseplatform.students
                            where email = %s
                            for update
                            """,
                            (email,),
                        ).fetchone()
                        if student:
                            break
            eligible = bool(
                student
                and student.get("status") in {"ACTIVE", "PENDING_VERIFICATION"}
            )
            if not throttled:
                if eligible:
                    conn.execute(
                        """
                        update courseplatform.student_password_resets
                        set invalidated_at = now(), status = 'INVALIDATED'
                        where student_id = %s and consumed_at is null
                          and invalidated_at is null and expires_at > now()
                        """,
                        (student["student_id"],),
                    )
                conn.execute(
                    """
                    insert into courseplatform.student_password_resets
                      (reset_id, student_id, email_hash, source_hash, token_hash,
                       status, expires_at, created_at)
                    values (%s, %s, %s, %s, %s, %s, %s, now())
                    """,
                    (
                        reset_id,
                        student["student_id"] if eligible else None,
                        email_hash,
                        source_hash,
                        runtime.hash_secret(token) if eligible else None,
                        "PENDING" if eligible else "IGNORED",
                        expires_at,
                    ),
                )
                if eligible:
                    runtime.audit(
                        conn,
                        "SYSTEM",
                        student["student_id"],
                        "STUDENT_PASSWORD_RESET_REQUESTED",
                        "STUDENT",
                        student["student_id"],
                        {"resetId": reset_id, "expiresAt": runtime.iso(expires_at)},
                    )
                    delivery = {"resetId": reset_id, "token": token}
            conn.commit()
    except Exception as error:
        raise runtime.database_api_error(error) from error

    result = password_reset_public_result(runtime.success)
    if delivery:
        result["_passwordResetDelivery"] = delivery
    return result


def complete_student_password_reset_action(payload: dict[str, Any], runtime: IdentityRuntime):
    runtime.require_fields(payload, ["token", "newPassword", "confirmPassword"])
    token = str_value(payload.get("token"))
    new_password = str(payload.get("newPassword") or "")
    confirmation = str(payload.get("confirmPassword") or "")
    if new_password != confirmation:
        raise ApiError("PASSWORD_CONFIRMATION_MISMATCH", "A confirmação da nova palavra-passe não corresponde.")
    if not valid_password(new_password) or len(new_password) > 128:
        raise ApiError("INVALID_NEW_PASSWORD", "A nova palavra-passe deve ter entre 8 e 128 caracteres.")
    if not token or len(token) > 256:
        raise ApiError("PASSWORD_RESET_TOKEN_INVALID", "O link de recuperação é inválido ou já expirou.")

    settings = runtime.get_settings()
    if len(settings.password_reset_hash_key.encode("utf-8")) < 32:
        raise ApiError("PASSWORD_RESET_UNAVAILABLE", "A recuperação de acesso não está disponível neste momento.")
    source = str_value(payload.get("_requestSource"))[:256] or "unknown"
    source_hash = password_reset_private_digest("source", source, settings)
    token_hash = runtime.hash_secret(token)
    reset_error = None
    student_id = ""
    try:
        with runtime.connection() as conn:
            conn.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (source_hash,))
            attempts = conn.execute(
                """
                select count(*) as count
                from courseplatform.student_password_reset_attempts
                where source_hash = %s
                  and created_at >= now() - (%s * interval '1 minute')
                """,
                (source_hash, max(1, settings.password_reset_completion_window_minutes)),
            ).fetchone() or {}
            if int(attempts.get("count") or 0) >= max(1, settings.password_reset_completion_limit):
                reset_error = ApiError(
                    "PASSWORD_RESET_RATE_LIMITED",
                    "Foram feitas demasiadas tentativas. Aguarde antes de tentar novamente.",
                )
            else:
                attempt_id = runtime.generate_id("PWA")
                conn.execute(
                    """
                    insert into courseplatform.student_password_reset_attempts
                      (attempt_id, source_hash, token_hash, succeeded, created_at)
                    values (%s, %s, %s, false, now())
                    """,
                    (attempt_id, source_hash, token_hash),
                )
                reset = conn.execute(
                    """
                    select r.*, s.status as student_status, s.email as student_email
                    from courseplatform.student_password_resets r
                    join courseplatform.students s on s.student_id = r.student_id
                    where r.token_hash = %s
                    for update of r, s
                    """,
                    (token_hash,),
                ).fetchone()
                expires_at = runtime.parse_datetime(reset.get("expires_at")) if reset else None
                valid_reset = bool(
                    reset
                    and reset.get("status") in {"PENDING", "DELIVERED"}
                    and not reset.get("consumed_at")
                    and not reset.get("invalidated_at")
                    and expires_at
                    and expires_at > runtime.utc_now()
                    and reset.get("student_status") in {"ACTIVE", "PENDING_VERIFICATION"}
                )
                if not valid_reset:
                    if reset and expires_at and expires_at <= runtime.utc_now():
                        conn.execute(
                            """
                            update courseplatform.student_password_resets
                            set status = 'EXPIRED', invalidated_at = coalesce(invalidated_at, now())
                            where reset_id = %s
                            """,
                            (reset["reset_id"],),
                        )
                    reset_error = ApiError(
                        "PASSWORD_RESET_TOKEN_INVALID",
                        "O link de recuperação é inválido ou já expirou.",
                    )
                else:
                    student_id = reset["student_id"]
                    conn.execute(
                        """
                        update courseplatform.students
                        set password_hash = crypt(%s, gen_salt('bf', 12)),
                            password_changed_at = now(), password_reset_required = false,
                            access_code = null, status = 'ACTIVE',
                            email_verified_at = coalesce(email_verified_at, now()),
                            updated_at = now()
                        where student_id = %s
                        """,
                        (new_password, student_id),
                    )
                    linked_admin_id = link_matching_legacy_staff(
                        conn,
                        student_id,
                        str_value(reset.get("student_email")),
                    )
                    if linked_admin_id:
                        runtime.audit(
                            conn,
                            "SYSTEM",
                            student_id,
                            "STAFF_IDENTITY_LINKED",
                            "ADMIN",
                            linked_admin_id,
                            {"studentId": student_id},
                        )
                    runtime.revoke_sessions(conn, student_id)
                    conn.execute(
                        """
                        update courseplatform.sessions ses
                        set active = false, revoked_at = now()
                        where ses.active = true
                          and ses.subject_id in (
                            select 'ADMIN:' || a.admin_id
                            from courseplatform.admins a
                            where a.student_id = %s
                          )
                        """,
                        (student_id,),
                    )
                    conn.execute(
                        """
                        update courseplatform.student_password_resets
                        set status = 'CONSUMED', consumed_at = now()
                        where reset_id = %s
                        """,
                        (reset["reset_id"],),
                    )
                    conn.execute(
                        """
                        update courseplatform.student_password_resets
                        set status = 'INVALIDATED', invalidated_at = now()
                        where student_id = %s and reset_id <> %s
                          and consumed_at is null and invalidated_at is null
                        """,
                        (student_id, reset["reset_id"]),
                    )
                    conn.execute(
                        """
                        update courseplatform.student_password_reset_attempts
                        set succeeded = true
                        where attempt_id = %s
                        """,
                        (attempt_id,),
                    )
                    runtime.create_student_notification(
                        conn,
                        student_id,
                        "GENERAL",
                        "Palavra-passe alterada",
                        "A palavra-passe da sua conta foi alterada através do processo de recuperação.",
                        action_url="#/profile",
                        entity_type="STUDENT",
                        entity_id=student_id,
                        priority="HIGH",
                        send_whatsapp=False,
                        send_email=False,
                        send_telegram=False,
                        send_push=False,
                    )
                    runtime.audit(
                        conn,
                        "SYSTEM",
                        student_id,
                        "STUDENT_PASSWORD_RESET_COMPLETED",
                        "STUDENT",
                        student_id,
                        {"resetId": reset["reset_id"], "sessionsRevoked": True},
                    )
            conn.commit()
    except ApiError:
        raise
    except Exception as error:
        raise runtime.database_api_error(error) from error

    if reset_error:
        raise reset_error
    return runtime.success({"passwordChanged": True, "sessionsRevoked": True})


def admin_login_action(payload: dict[str, Any], runtime: IdentityRuntime):
    runtime.require_fields(payload, ["email", "adminKey"])
    email = normalize_email(payload["email"])
    try:
        admin = runtime.fetch_one(
            """
            select a.*,
                   s.student_id as identity_student_id,
                   s.email as identity_email,
                   s.password_hash as identity_password_hash,
                   s.status as identity_status
            from courseplatform.admins a
            left join courseplatform.students s on s.student_id = a.student_id
            where lower(coalesce(s.email, a.email)) = %s
            order by (a.student_id is not null) desc
            limit 1
            """,
            (email,),
        )
    except Exception as error:
        raise runtime.database_api_error(error) from error
    linked_student = bool(admin and admin.get("student_id"))
    if (
        not admin
        or admin.get("status") != "ACTIVE"
        or (linked_student and admin.get("identity_status") != "ACTIVE")
    ):
        total = runtime.fetch_one("select count(*) as total from courseplatform.admins")
        if int(total.get("total") or 0) == 0:
            raise ApiError(
                "DATABASE_EMPTY",
                "A base de dados ligada ainda não tem administradores. Confirme se o POSTGRES_URL aponta para a base migrada.",
            )
        raise ApiError("INVALID_ADMIN_CREDENTIALS", "Credenciais administrativas invalidas.")
    try:
        password_hash = (
            admin.get("identity_password_hash")
            if linked_student
            else admin.get("password_hash")
        )
        if not runtime.verify_password(payload["adminKey"], password_hash):
            raise ApiError("INVALID_ADMIN_CREDENTIALS", "Credenciais administrativas invalidas.")
        subject_id = f"ADMIN:{admin['admin_id']}"
        with runtime.connection() as conn:
            runtime.revoke_sessions(conn, subject_id)
            session = runtime.create_session(
                conn,
                subject_id,
                payload.get("userAgent", ""),
                payload.get("ipHash", ""),
            )
            conn.commit()
    except ApiError:
        raise
    except Exception as error:
        raise runtime.database_api_error(error) from error
    return runtime.success({
        "adminToken": session["token"],
        "expiresAt": runtime.iso(session["expiresAt"]),
        "admin": runtime.public_admin(admin),
    })


def recover_admin_access_action(payload: dict[str, Any], runtime: IdentityRuntime):
    runtime.require_fields(payload, ["email", "recoveryKey"])
    if not runtime.configured_admin_recovery_hashes():
        raise ApiError(
            "ADMIN_RECOVERY_NOT_CONFIGURED",
            "A recuperação administrativa ainda não está configurada. Defina ADMIN_RECOVERY_KEY_HASH na Vercel.",
        )
    if not runtime.verify_admin_recovery_key(payload.get("recoveryKey")):
        raise ApiError("INVALID_ADMIN_RECOVERY_KEY", "Chave de recuperação administrativa inválida.")

    email = normalize_email(payload["email"])
    try:
        admin = runtime.fetch_one(
            """
            select a.*,
                   s.student_id as identity_student_id,
                   s.email as identity_email,
                   s.status as identity_status
            from courseplatform.admins a
            left join courseplatform.students s on s.student_id = a.student_id
            where lower(coalesce(s.email, a.email)) = %s
            order by (a.student_id is not null) desc
            limit 1
            """,
            (email,),
        )
    except Exception as error:
        raise runtime.database_api_error(error) from error
    linked_student = bool(admin and admin.get("student_id"))
    if (
        not admin
        or admin.get("status") != "ACTIVE"
        or (linked_student and admin.get("identity_status") != "ACTIVE")
    ):
        raise ApiError("ADMIN_RECOVERY_NOT_FOUND", "Não encontramos uma conta administrativa ativa com esse email.")
    if admin.get("role") != "OWNER":
        raise ApiError(
            "ADMIN_RECOVERY_OWNER_ONLY",
            "Revisores e administradores recuperam a palavra-passe através do email da conta de utilizador.",
        )

    admin_password = runtime.generate_access_code(14)
    try:
        with runtime.connection() as conn:
            if linked_student:
                conn.execute(
                    """
                    update courseplatform.students
                    set password_hash = crypt(%s, gen_salt('bf', 12)),
                        password_changed_at = now(), password_reset_required = true,
                        access_code = null, updated_at = now()
                    where student_id = %s
                    """,
                    (admin_password, admin["student_id"]),
                )
                conn.execute(
                    "update courseplatform.sessions set active = false, revoked_at = now() where subject_id = %s",
                    (admin["student_id"],),
                )
                row = admin
            else:
                row = conn.execute(
                    """
                    update courseplatform.admins
                    set password_hash = crypt(%s, gen_salt('bf', 12)),
                        password_changed_at = now(), password_reset_required = true,
                        updated_at = now()
                    where admin_id = %s
                    returning *
                    """,
                    (admin_password, admin["admin_id"]),
                ).fetchone()
            conn.execute(
                "update courseplatform.sessions set active = false, revoked_at = now() where subject_id = %s",
                (f"ADMIN:{admin['admin_id']}",),
            )
            runtime.audit(
                conn,
                "SYSTEM",
                "ADMIN_RECOVERY",
                "ADMIN_ACCESS_RECOVERED",
                "ADMIN",
                admin["admin_id"],
                {
                    "role": row.get("role"),
                    "email": runtime.mask_email(row.get("identity_email") or row.get("email") or email),
                    "identitySource": "STUDENT" if linked_student else "LEGACY_ADMIN",
                },
            )
            conn.commit()
    except Exception as error:
        raise runtime.database_api_error(error) from error

    return runtime.success({
        "admin": runtime.public_admin(row),
        "email": runtime.mask_email(row.get("identity_email") or row.get("email") or email),
        "temporaryAdminKey": admin_password,
    })


def logout_action(payload: dict[str, Any], runtime: IdentityRuntime):
    token = payload.get("sessionToken") or payload.get("adminToken")
    if token:
        runtime.prepare_chat_feature_schema()
        with runtime.connection() as conn:
            token_hash = runtime.hash_secret(token)
            session = conn.execute(
                "select subject_id from courseplatform.sessions where session_token = %s",
                (token_hash,),
            ).fetchone() or {}
            conn.execute(
                "update courseplatform.sessions set active = false, revoked_at = now() where session_token = %s",
                (token_hash,),
            )
            subject_id = str_value(session.get("subject_id"))
            actor_type = "ADMIN" if subject_id.startswith("ADMIN:") else "STUDENT"
            actor_id = subject_id.replace("ADMIN:", "", 1) if actor_type == "ADMIN" else subject_id
            if actor_id:
                conn.execute(
                    "delete from courseplatform.chat_presence where actor_type = %s and actor_id = %s",
                    (actor_type, actor_id),
                )
            conn.commit()
    return runtime.success({"loggedOut": True})


def admin_me_action(payload: dict[str, Any], runtime: IdentityRuntime):
    _, admin = runtime.admin_context(payload)
    return runtime.success({"admin": runtime.public_admin(admin)})


def update_my_profile_action(payload: dict[str, Any], runtime: IdentityRuntime):
    runtime.prepare_notification_feature_schema()
    _, student = runtime.student_context(payload)
    photo_url = str_value(payload.get("profilePhotoUrl") or student.get("profile_photo_url"))
    if str_value(payload.get("profilePhotoBase64")):
        mime_type = str_value(payload.get("profilePhotoMimeType") or "image/jpeg") or "image/jpeg"
        base64_data = str_value(payload.get("profilePhotoBase64"))
        photo_url = f"data:{mime_type};base64,{base64_data}"
    if runtime.as_bool(payload.get("removeProfilePhoto")):
        photo_url = ""

    whatsapp_opt_in = (
        runtime.as_bool(payload.get("whatsappOptIn"))
        if "whatsappOptIn" in payload else runtime.as_bool(student.get("whatsapp_opt_in"))
    )
    email_opt_in = (
        runtime.as_bool(payload.get("emailOptIn"))
        if "emailOptIn" in payload else runtime.as_bool(student.get("email_opt_in"))
    )
    telegram_opt_in = (
        runtime.as_bool(payload.get("telegramOptIn"))
        if "telegramOptIn" in payload else runtime.as_bool(student.get("telegram_opt_in"))
    )
    phone = str_value(payload.get("phone"))
    if whatsapp_opt_in and not runtime.normalize_whatsapp_recipient(phone):
        raise ApiError(
            "INVALID_WHATSAPP_PHONE",
            "Para ativar o WhatsApp, informe um telefone com indicativo internacional, por exemplo +258.",
        )
    if email_opt_in and not runtime.normalize_email_recipient(student.get("email")):
        raise ApiError("INVALID_NOTIFICATION_EMAIL", "A conta não possui um endereço de email válido.")
    if telegram_opt_in and not runtime.normalize_telegram_recipient(student.get("telegram_chat_id")):
        raise ApiError("TELEGRAM_LINK_REQUIRED", "Ligue primeiro a sua conta ao bot oficial do Telegram.")
    preferences = runtime.notification_preferences(student)
    supplied_preferences = payload.get("notificationPreferences")
    if isinstance(supplied_preferences, dict):
        for key in runtime.default_notification_preferences:
            if key in supplied_preferences:
                preferences[key] = runtime.as_bool(supplied_preferences[key])

    patch = {
        "full_name": str_value(payload.get("fullName") or student.get("full_name")),
        "country": str_value(payload.get("country")),
        "organization": str_value(payload.get("organization")),
        "phone": phone,
        "job_title": str_value(payload.get("jobTitle")),
        "interests": str_value(payload.get("interests")),
        "profile_photo_url": photo_url,
    }
    with runtime.connection() as conn:
        row = conn.execute(
            """
            update courseplatform.students
            set full_name = %s, country = %s, organization = %s, phone = %s,
                job_title = %s, interests = %s, profile_photo_url = %s,
                whatsapp_opt_in = %s,
                whatsapp_opt_in_at = case
                  when %s and not coalesce(whatsapp_opt_in, false) then now()
                  when not %s then null
                  else whatsapp_opt_in_at
                end,
                email_opt_in = %s,
                email_opt_in_at = case
                  when %s and not coalesce(email_opt_in, false) then now()
                  when not %s then null
                  else email_opt_in_at
                end,
                telegram_opt_in = %s,
                telegram_opt_in_at = case
                  when %s and not coalesce(telegram_opt_in, false) then now()
                  when not %s then null
                  else telegram_opt_in_at
                end,
                notification_preferences_json = %s::jsonb,
                updated_at = now()
            where student_id = %s
            returning *
            """,
            (
                patch["full_name"], patch["country"], patch["organization"], patch["phone"],
                patch["job_title"], patch["interests"], patch["profile_photo_url"],
                whatsapp_opt_in, whatsapp_opt_in, whatsapp_opt_in,
                email_opt_in, email_opt_in, email_opt_in,
                telegram_opt_in, telegram_opt_in, telegram_opt_in,
                json.dumps(preferences), student["student_id"],
            ),
        ).fetchone()
        runtime.audit(
            conn,
            "STUDENT",
            student["student_id"],
            "PROFILE_UPDATED",
            "STUDENT",
            student["student_id"],
            {"notificationConsent": {
                "whatsapp": whatsapp_opt_in,
                "email": email_opt_in,
                "telegram": telegram_opt_in,
            }},
        )
        conn.commit()
    return runtime.success({
        "student": runtime.public_student(row),
        "notificationChannelInfo": runtime.student_notification_channel_info(),
    })


def change_my_access_code_action(payload: dict[str, Any], runtime: IdentityRuntime):
    _, student = runtime.student_context(payload)
    runtime.require_fields(payload, ["currentAccessCode", "newAccessCode"])
    if not runtime.verify_password(payload["currentAccessCode"], student.get("password_hash")):
        raise ApiError("INVALID_CURRENT_ACCESS_CODE", "A palavra-passe atual não está correta.")
    new_code = str_value(payload.get("newAccessCode"))
    if not valid_password(new_code):
        raise ApiError("WEAK_ACCESS_CODE", "A nova palavra-passe deve ter pelo menos 8 caracteres.")
    if runtime.verify_password(new_code, student.get("password_hash")):
        raise ApiError("ACCESS_CODE_UNCHANGED", "A nova palavra-passe deve ser diferente da atual.")
    with runtime.connection() as conn:
        conn.execute(
            """
            update courseplatform.students
            set password_hash = crypt(%s, gen_salt('bf', 12)),
                password_changed_at = now(), password_reset_required = false,
                access_code = null, updated_at = now()
            where student_id = %s
            """,
            (new_code, student["student_id"]),
        )
        conn.execute(
            "update courseplatform.sessions set active = false, revoked_at = now() where subject_id = %s",
            (student["student_id"],),
        )
        conn.execute(
            """
            update courseplatform.sessions ses
            set active = false, revoked_at = now()
            where ses.active = true
              and ses.subject_id in (
                select 'ADMIN:' || a.admin_id
                from courseplatform.admins a
                where a.student_id = %s
              )
            """,
            (student["student_id"],),
        )
        runtime.audit(
            conn,
            "STUDENT",
            student["student_id"],
            "ACCESS_CODE_CHANGED",
            "STUDENT",
            student["student_id"],
        )
        conn.commit()
    return runtime.success({"requiresLogin": True})


def change_my_email_action(payload: dict[str, Any], runtime: IdentityRuntime):
    runtime.prepare_notification_feature_schema()
    runtime.require_fields(payload, ["currentAccessCode", "newEmail", "confirmEmail"])
    if not runtime.as_bool(payload.get("acknowledgeSecurityImpact")):
        raise ApiError(
            "EMAIL_CHANGE_ACKNOWLEDGEMENT_REQUIRED",
            "Confirme que compreende o encerramento das sessões e a suspensão das notificações por email.",
        )
    new_email = runtime.validated_email_change(payload)
    current_password = str_value(payload.get("currentAccessCode"))
    if len(current_password) > 1024:
        raise ApiError("INVALID_CURRENT_ACCESS_CODE", "A palavra-passe atual não está correta.")
    try:
        with runtime.connection() as conn:
            _, session_student = runtime.student_context_with_conn(conn, payload)
            student = conn.execute(
                "select * from courseplatform.students where student_id = %s for update",
                (session_student["student_id"],),
            ).fetchone()
            if not student or student.get("status") != "ACTIVE":
                raise ApiError("STUDENT_NOT_ACTIVE", "A conta do estudante não está ativa.")
            if not runtime.verify_password_with_conn(conn, current_password, student.get("password_hash")):
                raise ApiError("INVALID_CURRENT_ACCESS_CODE", "A palavra-passe atual não está correta.")
            row = runtime.secure_student_email_update(
                conn,
                student,
                new_email,
                actor_type="STUDENT",
                actor_id=student["student_id"],
                reason="Alteração solicitada no perfil pessoal.",
            )
            conn.commit()
    except ApiError:
        raise
    except Exception as error:
        text = str(error).lower()
        if "unique" in text or "duplicate" in text:
            raise ApiError("EMAIL_ALREADY_IN_USE", "Este endereço de email já está associado a outro estudante.") from error
        raise runtime.database_api_error(error) from error
    return runtime.success({
        "student": runtime.public_student(row),
        "email": new_email,
        "requiresLogin": True,
    })
