import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class Database:
    """
    Wraps engine + session creation behind simple methods so callers don't
    touch SQLAlchemy internals directly. One instance is created at module
    load (see `db` below) and reused everywhere.
    """

    def __init__(self, database_url: str, *, pool_size: int, max_overflow: int, pool_recycle: int):
        self._database_url = database_url
        self._is_sqlite = database_url.startswith("sqlite")

        connect_args = {"check_same_thread": False} if self._is_sqlite else {}
        engine_kwargs = dict(connect_args=connect_args)

        if not self._is_sqlite:
            engine_kwargs.update(
                pool_pre_ping=True,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_recycle=pool_recycle,
            )

        try:
            self.engine = create_engine(database_url, **engine_kwargs)
        except Exception:
            logger.exception("Failed to create database engine")
            raise

        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def get_session(self) -> Session:
        try:
            return self.SessionLocal()
        except Exception:
            logger.exception("Failed to open a new database session")
            raise

    def init_db(self) -> None:
        """Create tables if they don't exist. Fine for local dev; use Alembic migrations in prod."""
        try:
            from app.db import models  # noqa: F401 (ensures models are registered on Base)
            Base.metadata.create_all(bind=self.engine)
        except Exception:
            logger.exception("Failed to initialize database tables")
            raise

    def check_connection(self) -> bool:
        """Lightweight health check — used by /health. Returns False instead of raising."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            logger.exception("Database health check failed")
            return False


settings = get_settings()
db = Database(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
)
SessionLocal = db.SessionLocal  # backwards-compatible alias for existing callers (e.g. worker.py)


def get_db():
    """FastAPI dependency — unchanged usage: Depends(get_db)."""
    session = db.get_session()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Kept as a module-level function so main.py's existing import doesn't need to change."""
    db.init_db()