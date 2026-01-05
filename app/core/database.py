from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker#, declarative_base
from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.orm import declarative_base
from app.core.config import settings
import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)
logger.info("Intialise DentC Backend DB")

Base = declarative_base()

# Import models so they register with Base
import app.models  # noqa


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
