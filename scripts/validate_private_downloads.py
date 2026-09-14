"""Validate deployed private downloads with representative active sessions.

The script is read-only. Tokens are accepted only through environment variables
and are never printed. Database rows are used solely to select representative
objects and verify the bytes returned by the deployed API.
"""

import hashlib
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.courseplatform.config import get_settings
from backend.courseplatform.db import connection


class ValidationError(Exception):
    pass


@dataclass(frozen=True)
class StoredObject:
    entity_id: str
    checksum: str
    size_bytes: int


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValidationError(f"Variável obrigatória ausente: {name}")
    return value


def validation_base_url() -> str:
    value = (
        os.getenv("COURSEPLATFORM_VALIDATION_BASE_URL", "").strip()
        or os.getenv("PLATFORM_URL", "").strip()
    ).rstrip("/")
    if not value:
        raise ValidationError(
            "Defina COURSEPLATFORM_VALIDATION_BASE_URL com a origem publicada da API."
        )
    parsed = urlsplit(value)
    if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValidationError("A validação remota exige HTTPS.")
    return value


def session_actor(token: str, expected: str) -> dict:
    with connection() as conn:
        session = conn.execute(
            """
            select subject_id
            from courseplatform.sessions
            where session_token = %s and active = true and expires_at > now()
            """,
            (token,),
        ).fetchone()
        if not session:
            raise ValidationError(f"A sessão de {expected.lower()} não está ativa.")
        subject_id = str(session["subject_id"])
        if expected == "STUDENT":
            if subject_id.startswith("ADMIN:"):
                raise ValidationError("A sessão configurada para estudante pertence ao staff.")
            actor = conn.execute(
                "select student_id, status from courseplatform.students where student_id = %s",
                (subject_id,),
            ).fetchone()
            if not actor or actor.get("status") != "ACTIVE":
                raise ValidationError("O estudante de validação não está ativo.")
            return {"id": actor["student_id"], "role": "STUDENT"}

        if not subject_id.startswith("ADMIN:"):
            raise ValidationError(f"A sessão de {expected.lower()} não pertence ao staff.")
        actor = conn.execute(
            "select admin_id, role, status from courseplatform.admins where admin_id = %s",
            (subject_id.removeprefix("ADMIN:"),),
        ).fetchone()
        allowed = {"REVIEWER"} if expected == "REVIEWER" else {"ADMIN", "OWNER"}
        if not actor or actor.get("status") != "ACTIVE" or actor.get("role") not in allowed:
            raise ValidationError(f"A sessão configurada não possui o papel {expected}.")
        return {"id": actor["admin_id"], "role": actor["role"]}


def submission_sample(student_id: str | None = None, *, exclude_student_id: str | None = None) -> StoredObject | None:
    clauses = ["storage_status = 'READY'", "storage_checksum_sha256 is not null"]
    params = []
    if student_id:
        clauses.append("student_id = %s")
        params.append(student_id)
    if exclude_student_id:
        clauses.append("student_id <> %s")
        params.append(exclude_student_id)
    with connection() as conn:
        row = conn.execute(
            f"""
            select file_id, storage_checksum_sha256, size_bytes
            from courseplatform.files
            where {' and '.join(clauses)} and coalesce(status, 'ACTIVE') <> 'DELETED'
            order by uploaded_at desc nulls last, file_id
            limit 1
            """,
            tuple(params),
        ).fetchone()
    if not row:
        return None
    return StoredObject(row["file_id"], row["storage_checksum_sha256"], int(row["size_bytes"] or 0))


def receipt_sample() -> StoredObject | None:
    with connection() as conn:
        row = conn.execute(
            """
            select request_id, payment_receipt_checksum_sha256, payment_receipt_size_bytes
            from courseplatform.certificate_requests
            where payment_receipt_storage_status = 'READY'
              and payment_receipt_checksum_sha256 is not null
            order by submitted_at desc nulls last, request_id
            limit 1
            """
        ).fetchone()
    if not row:
        return None
    return StoredObject(
        row["request_id"],
        row["payment_receipt_checksum_sha256"],
        int(row["payment_receipt_size_bytes"] or 0),
    )


def request_download(base_url: str, path: str, header_name: str = "", token: str = "") -> tuple[int, bytes, dict]:
    headers = {"User-Agent": "courseplatform-private-download-validation/1.0"}
    if header_name and token:
        headers[header_name] = token
    request = urllib.request.Request(f"{base_url}{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as error:
        error.read(4096)
        return error.code, b"", dict(error.headers.items())


def assert_status(name: str, actual: int, expected: int) -> None:
    if actual != expected:
        raise ValidationError(f"{name}: HTTP {actual}; esperado HTTP {expected}.")
    print(f"{name}: status={actual} result=ok")


def assert_download(name: str, response: tuple[int, bytes, dict], expected: StoredObject) -> None:
    status, content, headers = response
    assert_status(name, status, 200)
    if expected.size_bytes and len(content) != expected.size_bytes:
        raise ValidationError(f"{name}: tamanho divergente.")
    if hashlib.sha256(content).hexdigest() != expected.checksum:
        raise ValidationError(f"{name}: checksum divergente.")
    if headers.get("Cache-Control", headers.get("cache-control", "")).lower() != "private, no-store":
        raise ValidationError(f"{name}: Cache-Control privado ausente.")
    disposition = headers.get("Content-Disposition", headers.get("content-disposition", "")).lower()
    if not disposition.startswith("attachment;"):
        raise ValidationError(f"{name}: resposta não foi marcada como download.")
    print(f"{name}: integrity=ok bytes={len(content)}")


def main() -> int:
    get_settings().require_database()
    base_url = validation_base_url()
    student_token = required_env("COURSEPLATFORM_VALIDATION_STUDENT_TOKEN")
    reviewer_token = required_env("COURSEPLATFORM_VALIDATION_REVIEWER_TOKEN")
    admin_token = required_env("COURSEPLATFORM_VALIDATION_ADMIN_TOKEN")

    student = session_actor(student_token, "STUDENT")
    session_actor(reviewer_token, "REVIEWER")
    session_actor(admin_token, "ADMIN")
    own_file = submission_sample(student["id"])
    staff_file = submission_sample()
    other_file = submission_sample(exclude_student_id=student["id"])
    receipt = receipt_sample()
    if not own_file or not staff_file or not receipt:
        raise ValidationError("Faltam objetos READY representativos para executar todos os casos.")

    file_path = f"/api/files/{quote(staff_file.entity_id, safe='')}/content?download=1"
    own_path = f"/api/files/{quote(own_file.entity_id, safe='')}/content?download=1"
    receipt_path = f"/api/certificate-requests/{quote(receipt.entity_id, safe='')}/receipt?download=1"

    assert_status("anonymous_submission", request_download(base_url, file_path)[0], 401)
    assert_download(
        "student_own_submission",
        request_download(base_url, own_path, "x-session-token", student_token),
        own_file,
    )
    if other_file:
        other_path = f"/api/files/{quote(other_file.entity_id, safe='')}/content?download=1"
        assert_status(
            "student_other_submission",
            request_download(base_url, other_path, "x-session-token", student_token)[0],
            404,
        )
    assert_download(
        "reviewer_submission",
        request_download(base_url, file_path, "x-admin-token", reviewer_token),
        staff_file,
    )
    assert_status(
        "reviewer_receipt",
        request_download(base_url, receipt_path, "x-admin-token", reviewer_token)[0],
        403,
    )
    assert_download(
        "admin_submission",
        request_download(base_url, file_path, "x-admin-token", admin_token),
        staff_file,
    )
    assert_download(
        "admin_receipt",
        request_download(base_url, receipt_path, "x-admin-token", admin_token),
        receipt,
    )
    print("private_download_validation=passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as error:
        print(f"private_download_validation=failed reason={error}", file=sys.stderr)
        raise SystemExit(1)
