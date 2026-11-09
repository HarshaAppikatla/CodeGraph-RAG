import os
import sys
import secrets
import logging
from typing import Optional
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("codegraph.config")

# Fallback ephemeral secret generated at startup if not configured
_EPHEMERAL_SECRET = secrets.token_urlsafe(32)


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./codegraph.db"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-flash-latest"
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_USER: Optional[str] = None
    NEO4J_PASSWORD: str = "password"
    QDRANT_HOST: Optional[str] = None
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_PATH: Optional[str] = None
    CORS_ORIGINS: Optional[str] = None
    GIT_ALLOWED_HOSTS: str = "github.com,gitlab.com,bitbucket.org"
    JWT_SECRET: str = _EPHEMERAL_SECRET
    ENCRYPTION_KEY: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    MAX_CONCURRENT_INGESTIONS_PER_USER: int = 1
    MAX_WORKSPACES_PER_USER: int = 25

    @property
    def neo4j_user(self) -> str:
        return self.NEO4J_USER or self.NEO4J_USERNAME or "neo4j"

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if not v or not v.strip():
            return _EPHEMERAL_SECRET
        cleaned = v.strip()
        if len(cleaned) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long.")
        return cleaned

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                return None
            if len(cleaned) < 32:
                raise ValueError("ENCRYPTION_KEY must be at least 32 characters long.")
            return cleaned
        return None

    @model_validator(mode="after")
    def verify_production_secrets(self):
        # Fail-fast on Render: Render sets RENDER=true automatically
        is_render = bool(os.getenv("RENDER"))
        if is_render:
            raw_jwt = os.getenv("JWT_SECRET", "").strip()
            if not raw_jwt or raw_jwt == _EPHEMERAL_SECRET or len(raw_jwt) < 32:
                raise RuntimeError(
                    "CRITICAL PRODUCTION ERROR: Running on Render (RENDER=true detected), but JWT_SECRET "
                    "is missing, empty, or shorter than 32 characters in environment variables! "
                    "Generate a secure key with 'openssl rand -hex 32' and configure JWT_SECRET in your Render Dashboard."
                )
            raw_enc = os.getenv("ENCRYPTION_KEY", "").strip()
            if not raw_enc:
                logger.warning(
                    "⚠️ ENCRYPTION_KEY is not set in Render; falling back to JWT_SECRET for credential vault. "
                    "To prevent token rotation from invalidating stored keys, configure a separate ENCRYPTION_KEY in Render."
                )
            elif len(raw_enc) < 32:
                raise RuntimeError(
                    "CRITICAL PRODUCTION ERROR: ENCRYPTION_KEY on Render must be at least 32 characters long."
                )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )


settings = Settings()
