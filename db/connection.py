import logging
import os
import time
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .models import Base

load_dotenv()
logger = logging.getLogger(__name__)

_engine = None
_SessionFactory = None

_INIT_RETRIES = 3
_INIT_BACKOFF_SECONDS = [2, 4, 8]


def _build_url() -> str:
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    user = os.getenv("MYSQL_USER", "vendor_admin")
    password = os.getenv("MYSQL_PASSWORD", "changeme")
    database = os.getenv("MYSQL_DATABASE", "vendor_master_db")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            _build_url(),
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=10,
            max_overflow=20,
            echo=False,
        )
    return _engine


def get_session_factory():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory


def get_session() -> Session:
    return get_session_factory()()


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.rollback()
        session.close()


def init_db():
    """Create all tables defined in the ORM models, with retry logic for startup races."""
    for attempt in range(_INIT_RETRIES):
        try:
            Base.metadata.create_all(get_engine())
            return
        except Exception:
            if attempt < _INIT_RETRIES - 1:
                wait = _INIT_BACKOFF_SECONDS[attempt]
                logger.warning(
                    "Database init attempt %d/%d failed, retrying in %ds...",
                    attempt + 1, _INIT_RETRIES, wait,
                )
                time.sleep(wait)
            else:
                raise
