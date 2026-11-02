import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import NullPool
from backend.app.config import settings

Base = declarative_base()

# 1. Resolve and normalize database URL
db_url = os.getenv("DATABASE_URL", getattr(settings, "DATABASE_URL", "sqlite:///./codegraph.db"))

# Fix legacy Heroku/Render Postgres URL prefixes and specify psycopg2 driver for SQLAlchemy
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

if db_url.startswith("sqlite"):
    engine_kwargs = {
        "pool_pre_ping": True,
        "connect_args": {"check_same_thread": False},
    }
elif "-pooler" in db_url:
    # Recommended for Neon / cloud PostgreSQL with PgBouncer connection pooling:
    # Use NullPool because PgBouncer handles connection pooling on the server side.
    # This prevents idle client-side connection pooling conflicts and SSL drop errors.
    engine_kwargs = {
        "poolclass": NullPool,
        "connect_args": {
            "connect_timeout": 15,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    }
else:
    # Direct / non-pooler cloud PostgreSQL
    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 60,
        "pool_size": 5,
        "max_overflow": 2,
        "connect_args": {
            "connect_timeout": 15,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    }

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
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            db.close()
        except Exception:
            try:
                db.invalidate()
            except Exception:
                pass


def init_db():
    """Initializes schema tables on startup and migrates columns if needed."""
    try:
        from backend.app.models.user import User  # noqa: F401
        from backend.app.models.workspace import Workspace  # noqa: F401
    except ImportError:
        try:
            from app.models.user import User  # noqa: F401
            from app.models.workspace import Workspace  # noqa: F401
        except ImportError:
            pass

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
                ws_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(workspaces)")).fetchall()]
                if "error_message" not in ws_cols:
                    conn.execute(text("ALTER TABLE workspaces ADD COLUMN error_message VARCHAR(1024)"))
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
                conn.execute(text("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS error_message VARCHAR(1024)"))
                conn.commit()
    except Exception as e:
        sys.stderr.write(f"⚠️ DB migration notice: {e}\n")
