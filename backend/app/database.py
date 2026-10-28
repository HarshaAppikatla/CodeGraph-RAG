import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.config import settings

Base = declarative_base()

# Attempt primary database connection; fall back to local SQLite if PostgreSQL is unreachable
database_url = settings.DATABASE_URL
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {"connect_timeout": 1}

try:
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    with engine.connect() as conn:
        pass
except Exception as e:
    sys.stderr.write(f"⚠️ Primary DATABASE_URL ({database_url}) connection failed: {e}\n")
    sys.stderr.write("🔄 Falling back to SQLite ('sqlite:///./codegraph.db') for seamless local development.\n")
    database_url = "sqlite:///./codegraph.db"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

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
