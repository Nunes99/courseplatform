import base64
import hashlib
import hmac
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

from .config import get_settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_secret(value: str) -> str:
    settings = get_settings()
    raw = f"{settings.password_pepper}|{value or ''}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def constant_time_equals(a: str | None, b: str | None) -> bool:
    return hmac.compare_digest(a or "", b or "")


def generate_token() -> str:
    raw = f"{uuid.uuid4()}{uuid.uuid4()}{uuid.uuid4()}{int(time.time() * 1000)}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def generate_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def generate_access_code(length: int = 12) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def session_expiry() -> datetime:
    return utc_now() + timedelta(hours=get_settings().session_hours)
