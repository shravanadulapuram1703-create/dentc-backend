from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import QueuePool
from app.core.config import settings
import logging
from app.core.logging import setup_logging
import os

logger = setup_logging()
logger = logging.getLogger(__name__)
logger.info("Intialise DentC Backend DB")

Base = declarative_base()

# Import models so they register with Base
import app.models  # noqa

# Connection pool configuration
# Formula: (2 * CPU cores) + effective_spindle_count
# For most applications: pool_size = 5-20, max_overflow = 10
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # Recycle connections after 1 hour

engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_timeout=POOL_TIMEOUT,
    pool_recycle=POOL_RECYCLE,
    pool_pre_ping=True,  # Verify connections before using
    echo=os.getenv("DB_ECHO", "false").lower() == "true",  # Set to true for SQL debugging
    connect_args={
        "connect_timeout": 10,
        "application_name": "dentc_backend"
    }
)

# Connection pool event listeners for monitoring
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Set PostgreSQL connection parameters"""
    with dbapi_conn.cursor() as cur:
        # Set statement timeout (30 seconds)
        cur.execute("SET statement_timeout = '30s'")
        # Set idle transaction timeout
        cur.execute("SET idle_in_transaction_session_timeout = '60s'")

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False  # Prevent lazy loading after commit
)


def get_db():
    
    logger.info(f"===============================> {Base.metadata.tables.keys()}")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
