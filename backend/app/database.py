import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.config import settings

Base = declarative_base()

# 1. Resolve and normalize database URL
db_url = os.getenv("DATABASE_URL", getattr(settings, "DATABASE_URL", "sqlite:///./codegraph.db"))

# Fix legacy Heroku/Render Postgres URL prefixes for SQLAlchemy
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

engine_kwargs = {"pool_pre_ping": True}
if db_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Recommended for Neon / cloud PostgreSQL with connection pooling
    engine_kwargs["pool_recycle"] = 300

try:
    engine = create_engine(db_url, **engine_kwargs)
    with engine.connect() as conn:
        pass
except Exception as e:
    sys.stderr.write(f"⚠️ Primary DATABASE_URL ({db_url}) connection notice: {e}\n")
    if not db_url.startswith("sqlite"):
        sys.stderr.write("🔄 Falling back to SQLite ('sqlite:///./codegraph.db') for local resilience.\n")
        db_url = "sqlite:///./codegraph.db"
        engine = create_engine(db_url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency that provides a transactional database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initializes schema tables on startup and migrates columns if needed."""
    Base.metadata.create_all(bind=engine)
    try:
        with engine.connect() as conn:
            from sqlalchemy import text
            driver = engine.url.drivername.lower()
            if "sqlite" in driver:
                cols = [row[1] for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()]
                new_cols = [
                    ("gemini_key_encrypted", "VARCHAR(512)"),
                    ("openai_key_encrypted", "VARCHAR(512)"),
                    ("anthropic_key_encrypted", "VARCHAR(512)"),
                    ("deepseek_key_encrypted", "VARCHAR(512)"),
                    ("groq_key_encrypted", "VARCHAR(512)"),
                    ("provider_keys_encrypted", "VARCHAR(4096)"),
                ]
                for col_name, col_type in new_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            elif "postgres" in driver:
                for col_name, col_type in [
                    ("gemini_key_encrypted", "VARCHAR(512)"),
                    ("openai_key_encrypted", "VARCHAR(512)"),
                    ("anthropic_key_encrypted", "VARCHAR(512)"),
                    ("deepseek_key_encrypted", "VARCHAR(512)"),
                    ("groq_key_encrypted", "VARCHAR(512)"),
                    ("provider_keys_encrypted", "VARCHAR(4096)"),
                ]:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                conn.commit()
    except Exception as e:
        sys.stderr.write(f"⚠️ DB migration notice: {e}\n")
