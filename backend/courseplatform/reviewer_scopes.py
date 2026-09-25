from typing import Any

from .contracts import ApiError


REVIEWER_SCOPE_TYPES = {"GLOBAL", "COURSE", "OFFERING", "GROUP"}


def admin_from_context(context: Any) -> dict[str, Any]:
    """Extract the staff record while tolerating legacy no-op test doubles."""
    if isinstance(context, tuple) and len(context) == 2 and isinstance(context[1], dict):
        return context[1]
    return {"role": "ADMIN", "admin_id": ""}


def reviewer_scope_predicate(
    admin: dict[str, Any],
    *,
    course_expr: str,
    offering_expr: str = "null",
    group_expr: str = "null",
) -> tuple[str, tuple[Any, ...]]:
    if (admin.get("role") or "").upper() != "REVIEWER":
        return "true", ()
    return (
        f"""
        exists (
          select 1
          from courseplatform.reviewer_scopes rs
          where rs.admin_id = %s
            and rs.status = 'ACTIVE'
            and (
              rs.scope_type = 'GLOBAL'
              or (rs.scope_type = 'COURSE' and rs.course_id = {course_expr})
              or (rs.scope_type = 'OFFERING' and rs.offering_id = {offering_expr})
              or (rs.scope_type = 'GROUP' and rs.group_id = {group_expr})
            )
        )
        """,
        (admin["admin_id"],),
    )


def reviewer_course_predicate(admin: dict[str, Any], course_expr: str) -> tuple[str, tuple[Any, ...]]:
    if (admin.get("role") or "").upper() != "REVIEWER":
        return "true", ()
    return (
        f"""
        exists (
          select 1
          from courseplatform.reviewer_scopes rs
          where rs.admin_id = %s
            and rs.status = 'ACTIVE'
            and (rs.scope_type = 'GLOBAL' or rs.course_id = {course_expr})
        )
        """,
        (admin["admin_id"],),
    )


def require_attempt_scope(conn: Any, admin: dict[str, Any], attempt_id: str) -> None:
    if (admin.get("role") or "").upper() != "REVIEWER":
        return
    allowed = conn.execute(
        """
        select 1
        from courseplatform.attempts a
        join courseplatform.lessons l on l.lesson_id = a.lesson_id
        left join courseplatform.lesson_progress lp on lp.progress_id = a.progress_id
        left join courseplatform.enrollments e on e.enrollment_id = lp.enrollment_id
        where a.attempt_id = %s
          and exists (
            select 1
            from courseplatform.reviewer_scopes rs
            where rs.admin_id = %s and rs.status = 'ACTIVE'
              and (
                rs.scope_type = 'GLOBAL'
                or (rs.scope_type = 'COURSE' and rs.course_id = l.course_id)
                or (rs.scope_type = 'OFFERING' and rs.offering_id = e.offering_id)
                or (rs.scope_type = 'GROUP' and rs.group_id = e.group_id)
              )
          )
        limit 1
        """,
        (attempt_id, admin["admin_id"]),
    ).fetchone()
    if not allowed:
        raise ApiError("REVIEWER_SCOPE_REQUIRED", "Esta operação está fora do seu âmbito de revisão.")


def require_course_scope(conn: Any, admin: dict[str, Any], course_id: str) -> None:
    if (admin.get("role") or "").upper() != "REVIEWER":
        return
    allowed = conn.execute(
        """
        select 1
        from courseplatform.reviewer_scopes rs
        where rs.admin_id = %s and rs.status = 'ACTIVE'
          and (rs.scope_type = 'GLOBAL' or rs.course_id = %s)
        limit 1
        """,
        (admin["admin_id"], course_id),
    ).fetchone()
    if not allowed:
        raise ApiError("REVIEWER_SCOPE_REQUIRED", "Este curso está fora do seu âmbito de revisão.")


def require_student_scope(conn: Any, admin: dict[str, Any], student_id: str) -> None:
    if (admin.get("role") or "").upper() != "REVIEWER":
        return
    allowed = conn.execute(
        """
        select 1
        from courseplatform.enrollments e
        where e.student_id = %s
          and coalesce(e.status, 'ACTIVE') <> 'CANCELLED'
          and exists (
            select 1
            from courseplatform.reviewer_scopes rs
            where rs.admin_id = %s and rs.status = 'ACTIVE'
              and (
                rs.scope_type = 'GLOBAL'
                or (rs.scope_type = 'COURSE' and rs.course_id = e.course_id)
                or (rs.scope_type = 'OFFERING' and rs.offering_id = e.offering_id)
                or (rs.scope_type = 'GROUP' and rs.group_id = e.group_id)
              )
          )
        limit 1
        """,
        (student_id, admin["admin_id"]),
    ).fetchone()
    if not allowed:
        raise ApiError("REVIEWER_SCOPE_REQUIRED", "Este estudante está fora do seu âmbito de revisão.")


def normalize_scope_payload(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ApiError("INVALID_REVIEWER_SCOPE", "O âmbito do revisor é inválido.")
        scope_type = str(item.get("scopeType") or "").strip().upper()
        course_id = str(item.get("courseId") or "").strip()
        offering_id = str(item.get("offeringId") or "").strip()
        group_id = str(item.get("groupId") or "").strip()
        if scope_type not in REVIEWER_SCOPE_TYPES:
            raise ApiError("INVALID_REVIEWER_SCOPE", "O tipo de âmbito do revisor é inválido.")
        if scope_type == "GLOBAL":
            course_id = offering_id = group_id = ""
        elif scope_type == "COURSE" and (not course_id or offering_id or group_id):
            raise ApiError("INVALID_REVIEWER_SCOPE", "Selecione apenas o curso para este âmbito.")
        elif scope_type == "OFFERING" and (not course_id or not offering_id or group_id):
            raise ApiError("INVALID_REVIEWER_SCOPE", "Selecione o curso e a turma para este âmbito.")
        elif scope_type == "GROUP" and (not course_id or not offering_id or not group_id):
            raise ApiError("INVALID_REVIEWER_SCOPE", "Selecione o curso, a turma e o grupo.")
        key = (scope_type, course_id, offering_id, group_id)
        if key not in seen:
            seen.add(key)
            normalized.append({
                "scopeType": scope_type,
                "courseId": course_id,
                "offeringId": offering_id,
                "groupId": group_id,
            })
    if any(item["scopeType"] == "GLOBAL" for item in normalized) and len(normalized) > 1:
        raise ApiError("INVALID_REVIEWER_SCOPE", "O âmbito global não pode ser combinado com âmbitos específicos.")
    return normalized


def replace_reviewer_scopes(
    conn: Any,
    *,
    admin_id: str,
    actor_admin_id: str,
    scopes: list[dict[str, str]],
    generate_id: Any,
) -> None:
    for scope in scopes:
        if scope["scopeType"] == "GLOBAL":
            continue
        course = conn.execute(
            "select course_id from courseplatform.courses where course_id = %s",
            (scope["courseId"],),
        ).fetchone()
        if not course:
            raise ApiError("INVALID_REVIEWER_SCOPE", "O curso selecionado não existe.")
        if scope["scopeType"] in {"OFFERING", "GROUP"}:
            offering = conn.execute(
                "select offering_id from courseplatform.course_offerings where offering_id = %s and course_id = %s",
                (scope["offeringId"], scope["courseId"]),
            ).fetchone()
            if not offering:
                raise ApiError("INVALID_REVIEWER_SCOPE", "A turma não pertence ao curso selecionado.")
        if scope["scopeType"] == "GROUP":
            group = conn.execute(
                """
                select group_id from courseplatform.groups
                where group_id = %s and course_id = %s and offering_id = %s
                """,
                (scope["groupId"], scope["courseId"], scope["offeringId"]),
            ).fetchone()
            if not group:
                raise ApiError("INVALID_REVIEWER_SCOPE", "O grupo não pertence à turma selecionada.")
    conn.execute("delete from courseplatform.reviewer_scopes where admin_id = %s", (admin_id,))
    for scope in scopes:
        conn.execute(
            """
            insert into courseplatform.reviewer_scopes
              (reviewer_scope_id, admin_id, scope_type, course_id, offering_id, group_id,
               status, created_by, created_at, updated_at)
            values (%s, %s, %s, nullif(%s, ''), nullif(%s, ''), nullif(%s, ''),
                    'ACTIVE', %s, now(), now())
            """,
            (
                generate_id("RS"), admin_id, scope["scopeType"], scope["courseId"],
                scope["offeringId"], scope["groupId"], actor_admin_id,
            ),
        )
