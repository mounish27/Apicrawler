from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Crawl limits
    max_depth: int = 3
    max_pages: int = 100
    requests_per_second: float = 4.0
    crawl_timeout_seconds: int = 300

    # Storage
    exports_dir: Path = Path("exports/generated")

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # Security
    allowed_domains: list[str] = []
    max_payload_bytes: int = 10 * 1024 * 1024  # 10 MB

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


settings = Settings()
