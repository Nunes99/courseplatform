import json
import re
from datetime import datetime, timezone
from typing import Any

from ..contracts import ApiError, database_api_error, iso, success
from ..db import connection
from ..security import generate_id, generate_token, hash_secret, session_expiry


PLATFORM_OPERATOR_ROLES = frozenset(
    {"GLOBAL_OWNER", "PLATFORM_ADMIN", "SUPPORT", "AUDITOR"}
)
ONBOARDING_STATUSES = frozenset(
    {
        "SUBMITTED",
        "UNDER_REVIEW",
        "NEEDS_INFORMATION",
        "READY_FOR_PROVISIONING",
        "REJECTED",
        "CANCELLED",
    }
)
ONBOARDING_TRANSITIONS = {
    "SUBMITTED": frozenset({"UNDER_REVIEW", "CANCELLED"}),
    "UNDER_REVIEW": frozenset(
        {"NEEDS_INFORMATION", "READY_FOR_PROVISIONING", "REJECTED", "CANCELLED"}
    ),
    "NEEDS_INFORMATION": frozenset({"UNDER_REVIEW", "CANCELLED"}),
    "READY_FOR_PROVISIONING": frozenset({"UNDER_REVIEW", "CANCELLED"}),
    "REJECTED": frozenset(),
    "CANCELLED": frozenset(),
}
PLATFORM_WRITE_ROLES = frozenset({"GLOBAL_OWNER", "PLATFORM_ADMIN"})
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def _platform_audit(
    conn,
    operator_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        insert into courseplatform.platform_audit_log
          (event_id, operator_id, action, entity_type, entity_id, details_json, created_at)
        values (%s, %s, %s, %s, %s, %s, now())
        """,
        (
            generate_id("PEV"),
            operator_id,
            action,
            entity_type,
            entity_id,
            json.dumps(details or {}),
        ),
    )


def _serialize_operator(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "operatorId": row["operator_id"],
        "studentId": row.get("student_id"),
        "fullName": row.get("full_name") or "",
        "email": row.get("email") or "",
        "role": row.get("operator_role") or "",
        "status": row.get("operator_status") or row.get("status") or "",
    }


def _serialize_organization(row: dict[str, Any]) -> dict[str, Any]:
    settings = row.get("settings_json") or {}
    return {
        "organizationId": row["organization_id"],
        "slug": row.get("slug") or "",
        "displayName": row.get("display_name") or "",
        "legalName": row.get("legal_name") or "",
        "status": row.get("status") or "",
        "settings": settings if isinstance(settings, dict) else {},
        "memberCount": int(row.get("member_count") or 0),
        "courseCount": int(row.get("course_count") or 0),
        "createdAt": iso(row.get("created_at")),
        "updatedAt": iso(row.get("updated_at")),
    }


def _serialize_onboarding(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "requestId": row["request_id"],
        "requestedSlug": row.get("requested_slug") or "",
        "displayName": row.get("display_name") or "",
        "legalName": row.get("legal_name") or "",
        "contactName": row.get("contact_name") or "",
        "contactEmail": row.get("contact_email") or "",
        "contactPhone": row.get("contact_phone") or "",
        "countryCode": row.get("country_code") or "",
        "websiteUrl": row.get("website_url") or "",
        "planCode": row.get("plan_code") or "STANDARD",
        "requestedFeatures": row.get("requested_features_json") or {},
        "branding": row.get("branding_json") or {},
        "domains": row.get("domains_json") or [],
        "status": row.get("status") or "",
        "applicantNotes": row.get("applicant_notes") or "",
        "reviewNotes": row.get("review_notes") or "",
        "submittedAt": iso(row.get("submitted_at")),
        "reviewedAt": iso(row.get("reviewed_at")),
        "updatedAt": iso(row.get("updated_at")),
    }


def _platform_context_with_conn(
    conn,
    token: str,
    allowed_roles: frozenset[str] | set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not token:
        raise ApiError("PLATFORM_SESSION_REQUIRED", "É necessária uma sessão global.")
    row = conn.execute(
        """
        select ses.*, op.student_id, op.operator_role,
               op.status as operator_status, s.full_name, s.email,
               s.status as identity_status
        from courseplatform.platform_sessions ses
        join courseplatform.platform_operators op on op.operator_id = ses.operator_id
        join courseplatform.students s on s.student_id = op.student_id
        where ses.session_token = %s
        for update of ses
        """,
        (hash_secret(token),),
    ).fetchone()
    now = datetime.now(timezone.utc)
    if not row or not row.get("active"):
        raise ApiError("INVALID_PLATFORM_SESSION", "A sessão global é inválida ou foi encerrada.")
    if row.get("expires_at") and row["expires_at"] <= now:
        conn.execute(
            """
            update courseplatform.platform_sessions
            set active = false, revoked_at = coalesce(revoked_at, now())
            where session_token = %s
            """,
            (hash_secret(token),),
        )
        conn.commit()
        raise ApiError("PLATFORM_SESSION_EXPIRED", "A sessão global expirou.")
    if row.get("operator_status") != "ACTIVE" or row.get("identity_status") != "ACTIVE":
        raise ApiError("PLATFORM_ACCESS_REVOKED", "O acesso global foi suspenso.")
    if allowed_roles and row.get("operator_role") not in allowed_roles:
        raise ApiError("PLATFORM_FORBIDDEN", "Não possui permissão para esta operação global.")
    conn.execute(
        """
        update courseplatform.platform_sessions
        set last_seen_at = now()
        where session_token = %s
          and (last_seen_at is null or last_seen_at < now() - interval '5 minutes')
        """,
        (hash_secret(token),),
    )
    return row, row


def create_platform_session(payload: dict[str, Any]) -> dict[str, Any]:
    email = _normalize_email(payload.get("email"))
    password = str(payload.get("password") or "")
    if not email or not password:
        raise ApiError("REQUIRED_FIELDS", "Email e palavra-passe são obrigatórios.")
    try:
        with connection() as conn:
            operator = conn.execute(
                """
                select op.*, s.full_name, s.email, s.password_hash,
                       s.status as identity_status,
                       op.status as operator_status
                from courseplatform.platform_operators op
                join courseplatform.students s on s.student_id = op.student_id
                where lower(s.email) = %s
                limit 1
                """,
                (email,),
            ).fetchone()
            password_ok = False
            if operator and operator.get("password_hash"):
                password_ok = bool(
                    conn.execute(
                        "select %s = crypt(%s, %s) as ok",
                        (operator["password_hash"], password, operator["password_hash"]),
                    ).fetchone().get("ok")
                )
            if (
                not operator
                or not password_ok
                or operator.get("operator_status") != "ACTIVE"
                or operator.get("identity_status") != "ACTIVE"
            ):
                raise ApiError("INVALID_PLATFORM_CREDENTIALS", "Credenciais globais inválidas.")
            token = generate_token()
            expires_at = session_expiry()
            conn.execute(
                """
                update courseplatform.platform_sessions
                set active = false, revoked_at = coalesce(revoked_at, now())
                where operator_id = %s and active = true
                """,
                (operator["operator_id"],),
            )
            conn.execute(
                """
                insert into courseplatform.platform_sessions
                  (session_token, operator_id, expires_at, active, user_agent, ip_hash)
                values (%s, %s, %s, true, %s, %s)
                """,
                (
                    hash_secret(token),
                    operator["operator_id"],
                    expires_at,
                    str(payload.get("userAgent") or "")[:512],
                    str(payload.get("ipHash") or "")[:256],
                ),
            )
            _platform_audit(
                conn,
                operator["operator_id"],
                "PLATFORM_SESSION_CREATED",
                "PLATFORM_OPERATOR",
                operator["operator_id"],
            )
            conn.commit()
    except ApiError:
        raise
    except Exception as error:
        raise database_api_error(error) from error
    return success(
        {
            "platformToken": token,
            "expiresAt": iso(expires_at),
            "operator": _serialize_operator(operator),
        }
    )


def current_platform_session(token: str) -> dict[str, Any]:
    try:
        with connection() as conn:
            session, operator = _platform_context_with_conn(conn, token)
            conn.commit()
    except ApiError:
        raise
    except Exception as error:
        raise database_api_error(error) from error
    return success(
        {
            "sessionActive": True,
            "expiresAt": iso(session.get("expires_at")),
            "operator": _serialize_operator(operator),
        }
    )


def delete_platform_session(token: str) -> dict[str, Any]:
    try:
        with connection() as conn:
            conn.execute(
                """
                update courseplatform.platform_sessions
                set active = false, revoked_at = coalesce(revoked_at, now())
                where session_token = %s
                """,
                (hash_secret(token),),
            )
            conn.commit()
    except Exception as error:
        raise database_api_error(error) from error
    return success({"loggedOut": True})


def submit_onboarding_request(payload: dict[str, Any]) -> dict[str, Any]:
    slug = str(payload.get("requestedSlug") or "").strip().lower()
    email = _normalize_email(payload.get("contactEmail"))
    if not SLUG_PATTERN.fullmatch(slug):
        raise ApiError("INVALID_ORGANIZATION_SLUG", "Use apenas letras minúsculas, números e hífen no identificador.")
    try:
        with connection() as conn:
            existing_organization = conn.execute(
                "select organization_id from courseplatform.organizations where lower(slug) = %s",
                (slug,),
            ).fetchone()
            if existing_organization:
                raise ApiError("ORGANIZATION_SLUG_UNAVAILABLE", "Este identificador institucional não está disponível.")
            existing = conn.execute(
                """
                select * from courseplatform.organization_onboarding_requests
                where idempotency_key = %s
                """,
                (payload["idempotencyKey"],),
            ).fetchone()
            if existing:
                if (
                    existing.get("requested_slug") != slug
                    or _normalize_email(existing.get("contact_email")) != email
                ):
                    raise ApiError(
                        "IDEMPOTENCY_KEY_CONFLICT",
                        "A chave idempotente já foi usada com dados diferentes.",
                    )
                return success({"request": _serialize_onboarding(existing), "replayed": True})
            recent_count = conn.execute(
                """
                select count(*) as total
                from courseplatform.organization_onboarding_requests
                where lower(contact_email) = %s
                  and submitted_at >= now() - interval '24 hours'
                """,
                (email,),
            ).fetchone()
            if int((recent_count or {}).get("total") or 0) >= 3:
                raise ApiError(
                    "ONBOARDING_RATE_LIMITED",
                    "Foram recebidos vários pedidos recentes para este email. Tente novamente mais tarde.",
                )
            row = conn.execute(
                """
                insert into courseplatform.organization_onboarding_requests
                  (request_id, idempotency_key, requested_slug, display_name, legal_name,
                   contact_name, contact_email, contact_phone, country_code, website_url,
                   plan_code, requested_features_json, applicant_notes)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning *
                """,
                (
                    generate_id("ONB"), payload["idempotencyKey"], slug,
                    str(payload.get("displayName") or "").strip(),
                    str(payload.get("legalName") or "").strip() or None,
                    str(payload.get("contactName") or "").strip(), email,
                    str(payload.get("contactPhone") or "").strip() or None,
                    str(payload.get("countryCode") or "").strip().upper() or None,
                    str(payload.get("websiteUrl") or "").strip() or None,
                    str(payload.get("planCode") or "STANDARD").strip().upper(),
                    json.dumps(payload.get("requestedFeatures") or {}),
                    str(payload.get("applicantNotes") or "").strip() or None,
                ),
            ).fetchone()
            _platform_audit(conn, None, "ONBOARDING_REQUEST_SUBMITTED", "ONBOARDING_REQUEST", row["request_id"], {"requestedSlug": slug})
            conn.commit()
    except ApiError:
        raise
    except Exception as error:
        if getattr(error, "sqlstate", "") == "23505":
            raise ApiError("ONBOARDING_REQUEST_EXISTS", "Já existe um pedido ativo para esta instituição.") from None
        raise database_api_error(error) from error
    return success({"request": _serialize_onboarding(row), "replayed": False})


def platform_dashboard(token: str) -> dict[str, Any]:
    try:
        with connection() as conn:
            session, operator = _platform_context_with_conn(conn, token)
            organization_rows = conn.execute(
                """
                select o.*,
                       (select count(*) from courseplatform.organization_memberships m
                        where m.organization_id = o.organization_id and m.status = 'ACTIVE') as member_count,
                       (select count(*) from courseplatform.courses c
                        where c.organization_id = o.organization_id and c.status <> 'DELETED') as course_count
                from courseplatform.organizations o
                order by o.created_at, o.organization_id
                """
            ).fetchall()
            request_rows = conn.execute(
                """
                select * from courseplatform.organization_onboarding_requests
                order by submitted_at desc, request_id desc
                limit 100
                """
            ).fetchall()
            conn.commit()
    except ApiError:
        raise
    except Exception as error:
        raise database_api_error(error) from error
    summary = {
        "organizations": len(organization_rows),
        "activeOrganizations": sum(row.get("status") == "ACTIVE" for row in organization_rows),
        "pendingOnboarding": sum(
            row.get("status") in {"SUBMITTED", "UNDER_REVIEW", "NEEDS_INFORMATION"}
            for row in request_rows
        ),
        "readyForProvisioning": sum(row.get("status") == "READY_FOR_PROVISIONING" for row in request_rows),
    }
    return success(
        {
            "operator": _serialize_operator(operator),
            "summary": summary,
            "organizations": [_serialize_organization(row) for row in organization_rows],
            "onboardingRequests": [_serialize_onboarding(row) for row in request_rows],
            "provisioningEnabled": False,
        }
    )


def update_onboarding_request(token: str, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    target_status = str(payload.get("status") or "").strip().upper()
    if target_status not in ONBOARDING_STATUSES:
        raise ApiError("INVALID_ONBOARDING_STATUS", "Estado de onboarding inválido.")
    try:
        with connection() as conn:
            _session, operator = _platform_context_with_conn(conn, token, PLATFORM_WRITE_ROLES)
            current = conn.execute(
                """
                select * from courseplatform.organization_onboarding_requests
                where request_id = %s
                for update
                """,
                (request_id,),
            ).fetchone()
            if not current:
                raise ApiError("ONBOARDING_REQUEST_NOT_FOUND", "Pedido de onboarding não encontrado.")
            if target_status != current["status"] and target_status not in ONBOARDING_TRANSITIONS[current["status"]]:
                raise ApiError("INVALID_ONBOARDING_TRANSITION", "Esta mudança de estado não é permitida.")
            updated = conn.execute(
                """
                update courseplatform.organization_onboarding_requests
                set status = %s,
                    review_notes = %s,
                    reviewed_by_operator_id = %s,
                    reviewed_at = now(),
                    updated_at = now()
                where request_id = %s
                returning *
                """,
                (
                    target_status,
                    str(payload.get("reviewNotes") or "").strip() or None,
                    operator["operator_id"],
                    request_id,
                ),
            ).fetchone()
            _platform_audit(
                conn,
                operator["operator_id"],
                "ONBOARDING_STATUS_CHANGED",
                "ONBOARDING_REQUEST",
                request_id,
                {"from": current["status"], "to": target_status},
            )
            conn.commit()
    except ApiError:
        raise
    except Exception as error:
        raise database_api_error(error) from error
    return success({"request": _serialize_onboarding(updated), "provisioningEnabled": False})
