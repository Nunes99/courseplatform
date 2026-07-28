import os
import re
from functools import lru_cache
from urllib.parse import quote, urlsplit, urlunsplit

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


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _project_ref_from_supabase_url() -> str:
    supabase_url = _env("SUPABASE_URL") or _env("NEXT_PUBLIC_SUPABASE_URL")
    if not supabase_url:
        return ""
    hostname = urlsplit(supabase_url).hostname or ""
    return hostname.split(".")[0] if hostname.endswith(".supabase.co") else ""


def _postgres_user_for_host(host: str) -> str:
    user = _env("POSTGRES_USER")
    if user:
        return user
    project_ref = _project_ref_from_supabase_url()
    if project_ref and "pooler.supabase.com" in host:
        return f"postgres.{project_ref}"
    return "postgres"


def _build_postgres_url(host: str, database: str, password: str, user: str = "", port: str = "") -> str:
    selected_user = user or _postgres_user_for_host(host)
    selected_port = port or ("6543" if "pooler.supabase.com" in host else "5432")
    return (
        f"postgresql://{quote(selected_user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{selected_port}/{database or 'postgres'}?sslmode=require"
    )


def resolve_database_url() -> tuple[str, str, list[str]]:
    for name in ("DATABASE_URL", "POSTGRES_URL", "POSTGRES_URL_NON_POOLING", "POSTGRES_PRISMA_URL"):
        value = _env(name)
        if value:
            return normalize_database_url(value), name, []

    host = _env("POSTGRES_HOST")
    database = _env("POSTGRES_DATABASE") or _env("POSTGRES_DB") or "postgres"
    password = _env("POSTGRES_PASSWORD")
    user = _env("POSTGRES_USER")
    port = _env("POSTGRES_PORT")
    if host and password:
        return normalize_database_url(_build_postgres_url(host, database, password, user, port)), "POSTGRES_*", []

    project_ref = _project_ref_from_supabase_url()
    if project_ref and password:
        url = _build_postgres_url(f"db.{project_ref}.supabase.co", database, password, user or "postgres", port or "5432")
        return normalize_database_url(url), "SUPABASE_URL+POSTGRES_PASSWORD", []

    issues = []
    if not host and not project_ref:
        issues.append("Defina DATABASE_URL, POSTGRES_URL, POSTGRES_HOST ou SUPABASE_URL")
    if (host or project_ref) and not password:
        issues.append("Defina POSTGRES_PASSWORD; chaves SUPABASE_* nao sao senha Postgres")
    return "", "", issues


def database_url_diagnostics(value: str, source: str = "", preflight_issues: list[str] | None = None) -> dict:
    text = (value or "").strip()
    if not text:
        return {
            "configured": False,
            "source": source,
            "host": "",
            "port": "",
            "database": "",
            "sslmode": "",
            "issues": preflight_issues or ["DATABASE_URL ausente"],
        }

    normalized = normalize_database_url(text)
    parts = urlsplit(normalized)
    issues = list(preflight_issues or [])
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
        "source": source,
        "host": parts.hostname or "",
        "port": port,
        "database": (parts.path or "").lstrip("/"),
        "sslmode": "require" if "sslmode=require" in normalized else "",
        "issues": issues,
    }


class Settings:
    def __init__(self):
        database_url, database_source, database_issues = resolve_database_url()
        self.database_url = database_url
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
        self.database_diagnostics = database_url_diagnostics(database_url, database_source, database_issues)

    def require_database(self) -> None:
        if not self.database_url:
            raise RuntimeError("Postgres database connection is not configured.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
