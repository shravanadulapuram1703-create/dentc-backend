from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException, status
import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)



def set_tenant_schema(db: Session, schema_name: str):
    """
    Sets PostgreSQL schema for the current session
    """
    logger.info(f"schema_name -->  {schema_name}")
    db.execute( text('SET search_path TO :schema, public'),{"schema": schema_name})


def validate_tenant_switch(is_superuser: bool, target_tenant: str):
    if target_tenant and not is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can switch tenants"
        )
