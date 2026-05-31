"""
Service layer for Procedure Codes and Categories.
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_, func as sql_func
from typing import List, Optional
from fastapi import HTTPException, status

from app.api.v1.scheduler.models import ProcedureCode, ProcedureCategory
from app.api.v1.scheduler.schemas import (
    ProcedureCodeResponse,
    ProcedureCodeRequirements,
    ProcedureCategoryResponse
)


def get_procedure_codes(
    db: Session,
    category: Optional[str] = None,
    search: Optional[str] = None
) -> List[ProcedureCodeResponse]:
    """
    Get procedure codes with optional filtering.
    
    Args:
        db: Database session
        category: Filter by category
        search: Search in code, user_code, or description
    
    Returns:
        List of procedure codes
    """
    query = db.query(ProcedureCode)
    
    # Apply category filter
    if category and category != "ALL":
        query = query.filter(ProcedureCode.category == category)
    
    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                ProcedureCode.code.ilike(search_term),
                ProcedureCode.user_code.ilike(search_term),
                ProcedureCode.description.ilike(search_term)
            )
        )
    
    # Order by code
    codes = query.order_by(ProcedureCode.code).all()
    
    # Convert to response format
    result = []
    for code in codes:
        result.append(ProcedureCodeResponse(
            code=code.code,
            userCode=code.user_code or "-",
            description=code.description,
            category=code.category,
            requirements=ProcedureCodeRequirements(
                tooth=code.requires_tooth,
                surface=code.requires_surface,
                quadrant=code.requires_quadrant,
                materials=code.requires_materials
            ),
            defaultFee=float(code.default_fee),
            defaultDuration=code.default_duration
        ))
    
    return result


def get_procedure_categories(db: Session) -> List[ProcedureCategoryResponse]:
    """
    Get all procedure categories.
    
    Args:
        db: Database session
    
    Returns:
        List of procedure categories
    """
    categories = db.query(ProcedureCategory).order_by(ProcedureCategory.id).all()
    
    return [
        ProcedureCategoryResponse(
            id=cat.id,
            name=cat.name,
            displayName=cat.display_name
        )
        for cat in categories
    ]
