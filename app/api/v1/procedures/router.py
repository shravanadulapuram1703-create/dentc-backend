"""
API routes for Procedure Codes and Categories.
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.api.v1.auth.dependencies import get_current_user
from app.models.user import User
from app.api.v1.procedures.services import get_procedure_codes, get_procedure_categories
from app.api.v1.scheduler.schemas import (
    ProcedureCodesResponse,
    ProcedureCategoriesResponse
)

router = APIRouter(prefix="/procedures", tags=["procedures"])


@router.get("/codes", response_model=ProcedureCodesResponse)
def get_procedure_codes_api(
    category: Optional[str] = Query(None, description="Filter by procedure category"),
    search: Optional[str] = Query(None, description="Search in code, userCode, or description"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get procedure codes with optional filtering.
    
    Query Parameters:
    - category: Filter by procedure category (e.g., "DIAGNOSTIC")
    - search: Search term to filter codes
    
    Returns:
    - List of procedure codes matching the filters
    """
    codes = get_procedure_codes(db=db, category=category, search=search)
    return ProcedureCodesResponse(procedure_codes=codes)


@router.get("/categories", response_model=ProcedureCategoriesResponse)
def get_procedure_categories_api(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all procedure categories.
    
    Returns:
    - List of all procedure categories
    """
    categories = get_procedure_categories(db=db)
    return ProcedureCategoriesResponse(categories=categories)
