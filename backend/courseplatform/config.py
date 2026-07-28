import os
import re
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()


def _int_env(name: str, fallback: int) -> int:
    try:
        return int(os.getenv(name, str(fallback)))
    except ValueError:
        return fallback


def _fix_invalid_percent_encoding(value: str) -> str:
    return re.sub(r"%(?![0-9A-Fa-f]{2})", "%25", value)


def normalize_database_url(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if not text.startswith(("postgres://", "postgresql://")):
        return text

    parts = urlsplit(text)
    userinfo, separator, hostinfo = parts.netloc.rpartition("@")
    if separator:
        userinfo = _fix_invalid_percent_encoding(userinfo)
        return urlunsplit((parts.scheme, f"{userinfo}@{hostinfo}", parts.path, parts.query, parts.fragment))
    return text


def database_url_diagnostics(value: str) -> dict:
    text = (value or "").strip()
    if not text:
        return {
            "configured": False,
            "host": "",
            "port": "",
            "database": "",
            "sslmode": "",
            "issues": ["DATABASE_URL ausente"],
        }

    normalized = normalize_database_url(text)
    parts = urlsplit(normalized)
    issues = []
    if not parts.scheme.startswith("postgres"):
        issues.append("DATABASE_URL deve iniciar com postgresql:// ou postgres://")
    if not parts.hostname:
        issues.append("Host do Postgres ausente")
    if "supabase.com" in normalized and "sslmode=require" not in normalized:
        issues.append("Adicionar sslmode=require")
    if normalized != text:
        issues.append("DATABASE_URL tinha % bruto e foi normalizada em runtime")
    try:
        port = str(parts.port or "")
    except ValueError:
        port = ""
        issues.append("Porta do Postgres invalida")

    return {
        "configured": True,
        "host": parts.hostname or "",
        "port": port,
        "database": (parts.path or "").lstrip("/"),
        "sslmode": "require" if "sslmode=require" in normalized else "",
        "issues": issues,
    }


class Settings:
    def __init__(self):
        self.database_url = normalize_database_url(os.getenv("DATABASE_URL", ""))
        self.default_course_id = os.getenv("DEFAULT_COURSE_ID", "COURSE-EAPI-001")
        self.session_hours = _int_env("SESSION_HOURS", 12)
        self.db_connect_timeout = _int_env("DB_CONNECT_TIMEOUT", 15)
        self.db_connect_retries = _int_env("DB_CONNECT_RETRIES", 3)
        self.cors_origins = [
            item.strip()
            for item in os.getenv("CORS_ORIGINS", "*").split(",")
            if item.strip()
        ]
        self.app_version = os.getenv("APP_VERSION", "python-supabase-preview")
        self.database_diagnostics = database_url_diagnostics(os.getenv("DATABASE_URL", ""))

    def require_database(self) -> None:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
