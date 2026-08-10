import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "Leaf Online Store")
    APP_ENV: str = os.getenv("APP_ENV", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "change-this-secret-key",
    )

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://leaf_store_user:password@127.0.0.1:5432/leaf_store_db",
    )

    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8070"))

    BASE_URL: str = os.getenv(
        "BASE_URL",
        "https://leaf.ads-ai.in",
    )

    SESSION_COOKIE_NAME: str = os.getenv(
        "SESSION_COOKIE_NAME",
        "leaf_store_session",
    )

    SESSION_MAX_AGE: int = int(
        os.getenv("SESSION_MAX_AGE", "86400")
    )

    UPLOAD_DIR: Path = Path(
        os.getenv(
            "UPLOAD_DIR",
            str(BASE_DIR / "app" / "uploads"),
        )
    )

    MAX_UPLOAD_SIZE_MB: int = int(
        os.getenv("MAX_UPLOAD_SIZE_MB", "10")
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
