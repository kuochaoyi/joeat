"""Application settings. Everything comes from environment variables / backend/.env (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres@127.0.0.1:5432/joeat"

    # Privacy: LINE user / group ids are never stored raw, only HMAC-SHA256(secret, id).
    id_hash_secret: str = "dev-only-change-me"

    # "dev": the client may send any line_user_id (used by the browser demo without LIFF).
    # "line": the client must send a LIFF ID token which is verified against LINE.
    auth_mode: str = "dev"

    # LINE Messaging API / LIFF
    line_channel_id: str = ""
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    line_skip_signature: bool = False          # tests / local curl only
    line_dry_run: bool = True                  # do not call LINE; return the messages that would be sent
    liff_id: str = ""
    frontend_url: str = "http://localhost:3000"

    # Safety switch: test-fixture evidence (seed_restaurants.sql, source_type='test_fixture') is hidden unless this is true.
    allow_test_evidence: bool = False

    # Operator / reviewer API (/ops/*). Empty = the whole API is disabled (503). One shared key + a self-asserted X-Ops-User name for the audit trail:
    # good enough for a pilot with a handful of operators, NOT a substitute for real accounts.
    ops_api_key: str = ""

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
