import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.database import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    name = Column(String(255), nullable=False)
    repo_url = Column(String(512), nullable=False)
    type = Column(String(50), default="git")  # 'git' or 'zip'
    branch = Column(String(100), default="main")
    files_count = Column(Integer, default=0)
    nodes_count = Column(Integer, default=0)
    edges_count = Column(Integer, default=0)
    status = Column(String(50), default="INDEXING")  # 'INDEXING', 'READY', 'FAILED'
    language = Column(String(100), default="Java / Spring Boot")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="workspaces")
