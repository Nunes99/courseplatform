import os
from functools import lru_cache


def _int_env(name: str, fallback: int) -> int:
    try:
        return int(os.getenv(name, str(fallback)))
    except ValueError:
        return fallback


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")
    password_pepper: str = os.getenv("PASSWORD_PEPPER", "")
    admin_master_key_hash: str = os.getenv("ADMIN_MASTER_KEY_HASH", "")
    default_course_id: str = os.getenv("DEFAULT_COURSE_ID", "COURSE-EAPI-001")
    session_hours: int = _int_env("SESSION_HOURS", 12)
    cors_origins: list[str] = [
        item.strip()
        for item in os.getenv("CORS_ORIGINS", "*").split(",")
        if item.strip()
    ]
    app_version: str = os.getenv("APP_VERSION", "python-supabase-preview")

    def require_database(self) -> None:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
