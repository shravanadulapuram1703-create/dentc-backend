"""Office Assignment DTOs (gaps #24–#32).

Read shapes for each assignable catalog are derived from the target model (named
``Assigned*`` to avoid clashing with the catalog's own CRUD components). The
bulk-set bodies carry the id list; id type matches the catalog PK.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.models import (
    CodeBundle,
    LetterTemplate,
    NoteMacro,
    PrescriptionLibrary,
    ProcedureCode,
    ProductionType,
    Provider,
)
from app.schemas.factory import build_schemas

# Assigned-catalog read schemas (reuse the model fields under a distinct name).
AssignedProcedureCodeRead = build_schemas(ProcedureCode, "AssignedProcedureCode")[2]
AssignedCodeBundleRead = build_schemas(CodeBundle, "AssignedCodeBundle")[2]
AssignedProductionTypeRead = build_schemas(ProductionType, "AssignedProductionType")[2]
AssignedProviderRead = build_schemas(Provider, "AssignedProvider")[2]
AssignedNoteMacroRead = build_schemas(NoteMacro, "AssignedNoteMacro")[2]
AssignedPrescriptionRead = build_schemas(PrescriptionLibrary, "AssignedPrescription")[2]
AssignedLetterTemplateRead = build_schemas(LetterTemplate, "AssignedLetterTemplate")[2]


# Bulk-set bodies (string-id vs int-id catalogs).
class StrIdAssignmentSet(BaseModel):
    ids: list[str] = Field(default_factory=list, description="Full assigned set (replaces existing)")


class IntIdAssignmentSet(BaseModel):
    ids: list[int] = Field(default_factory=list, description="Full assigned set (replaces existing)")


class OfficeUsersSet(BaseModel):
    user_ids: list[int] = Field(default_factory=list, description="Full assigned user set (replaces existing)")
