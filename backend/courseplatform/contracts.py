import base64
import binascii
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from .storage import StorageError


class ApiError(Exception):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def success(data: dict[str, Any]) -> dict[str, Any]:
    return {"success": True, "data": data}


def public_error(error: Exception) -> dict[str, Any]:
    if isinstance(error, ApiError):
        return {
            "success": False,
            "error": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        }
    return {
        "success": False,
        "error": {
            "code": "API_ERROR",
            "message": "Ocorreu um erro interno ao processar o pedido.",
            "details": None,
        },
    }


def database_api_error(error: Exception) -> ApiError:
    error_name = error.__class__.__name__
    text = str(error).lower()
    if "undefinedcolumn" in text or "undefinedtable" in text or error_name == "ProgrammingError":
        return ApiError(
            "DATABASE_SCHEMA_ERROR",
            "A base de dados está ligada, mas o esquema e as tabelas da plataforma não estão completos.",
            {"errorType": error_name},
        )
    if "authentication" in text or "password" in text or "ecircuitbreaker" in text:
        return ApiError(
            "DATABASE_AUTH_ERROR",
            "A API não conseguiu autenticar no Postgres. Verifique POSTGRES_URL/POSTGRES_PASSWORD no Vercel.",
            {"errorType": error_name},
        )
    if error_name == "InsufficientPrivilege" or "permission denied" in text:
        return ApiError(
            "DATABASE_PERMISSION_ERROR",
            "A role de execução da API não possui uma permissão necessária.",
            {"errorType": error_name},
        )
    return ApiError(
        "DATABASE_UNAVAILABLE",
        "A base de dados não está disponível neste momento.",
        {"errorType": error_name},
    )


def storage_api_error(error: StorageError) -> ApiError:
    return ApiError(error.code, error.message)


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes", "sim"}


def str_value(value: Any) -> str:
    return str(value or "").strip()


def int_value(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return fallback


def float_value(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def parse_datetime(value: Any):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def require_fields(payload: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if payload.get(field) in (None, "")]
    if missing:
        raise ApiError("REQUIRED_FIELDS", "Campos obrigatorios ausentes.", missing)


def pagination(payload: dict[str, Any], default_limit: int = 100, max_limit: int = 500):
    limit = int(payload.get("limit") or default_limit)
    page = int(payload.get("page") or 1)
    limit = max(1, min(limit, max_limit))
    offset = payload.get("offset")
    offset = int(offset) if offset not in (None, "") else (max(1, page) - 1) * limit
    return limit, max(0, offset), max(1, page)


def cursor_page_limit(payload: dict[str, Any], default_limit: int = 50, max_limit: int = 500) -> int:
    return max(1, min(int_value(payload.get("limit"), default_limit), max_limit))


def cursor_scope(kind: str, *values: Any) -> str:
    serialized = json.dumps([kind, *values], ensure_ascii=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def encode_list_cursor(kind: str, scope: str, sort_at: Any, record_id: Any) -> str:
    payload = {
        "v": 1,
        "kind": kind,
        "scope": scope,
        "sortAt": iso(sort_at),
        "id": str_value(record_id),
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def decode_list_cursor(
    value: Any,
    kind: str,
    scope: str,
    *,
    allow_null_sort: bool = False,
    sort_type: str = "datetime",
) -> tuple[Any, str] | None:
    text = str_value(value)
    if not text:
        return None
    if len(text) > 1024:
        raise ApiError("INVALID_CURSOR", "O cursor de paginação é inválido.")
    try:
        padding = "=" * ((4 - len(text) % 4) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(f"{text}{padding}").decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError("INVALID_CURSOR", "O cursor de paginação é inválido.") from None
    if not isinstance(decoded, dict) or decoded.get("v") != 1:
        raise ApiError("INVALID_CURSOR", "O cursor de paginação é inválido.")
    if decoded.get("kind") != kind or not hmac.compare_digest(str(decoded.get("scope") or ""), scope):
        raise ApiError("CURSOR_FILTER_MISMATCH", "Os filtros mudaram. Reinicie a paginação.")
    record_id = str_value(decoded.get("id"))
    raw_sort = decoded.get("sortAt")
    if sort_type == "datetime":
        sort_at = parse_datetime(raw_sort)
    elif sort_type == "number":
        try:
            sort_at = float(raw_sort) if raw_sort not in (None, "") else None
        except (TypeError, ValueError):
            sort_at = None
    elif sort_type == "text":
        sort_at = str(raw_sort) if raw_sort is not None else None
    else:
        raise ValueError(f"Tipo de cursor não suportado: {sort_type}")
    if not record_id or (sort_at is None and not allow_null_sort):
        raise ApiError("INVALID_CURSOR", "O cursor de paginação é inválido.")
    return sort_at, record_id


def cursor_pagination_result(
    rows: list[dict[str, Any]],
    limit: int,
    kind: str,
    scope: str,
    sort_field: str,
    id_field: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    has_more = len(rows) > limit
    visible_rows = rows[:limit]
    next_cursor = ""
    if has_more and visible_rows:
        last = visible_rows[-1]
        next_cursor = encode_list_cursor(kind, scope, last.get(sort_field), last.get(id_field))
    return visible_rows, {
        "limit": limit,
        "returned": len(visible_rows),
        "hasMore": has_more,
        "nextCursor": next_cursor,
    }
