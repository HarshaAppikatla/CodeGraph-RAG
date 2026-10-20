import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.config import settings

Base = declarative_base()

# Attempt primary database connection; fall back to local SQLite if PostgreSQL is unreachable
database_url = settings.DATABASE_URL
connect_args = {}
if database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

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
    """Initializes schema tables on startup."""
    Base.metadata.create_all(bind=engine)
