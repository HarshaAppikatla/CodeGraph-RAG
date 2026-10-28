import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship
from backend.app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(100), default="Software Engineer")
    gemini_key_encrypted = Column(String(512), nullable=True)
    openai_key_encrypted = Column(String(512), nullable=True)
    anthropic_key_encrypted = Column(String(512), nullable=True)
    deepseek_key_encrypted = Column(String(512), nullable=True)
    groq_key_encrypted = Column(String(512), nullable=True)
    provider_keys_encrypted = Column(String(4096), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    workspaces = relationship("Workspace", back_populates="user", cascade="all, delete-orphan")
