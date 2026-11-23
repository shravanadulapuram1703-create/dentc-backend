"""Read / request models of the report engine API (02 §13).

Walking-skeleton subset: the catalog envelope. ENG-03 adds ReportDefinitionRead,
ENG-05 the validate models, ENG-12/13 runs and result pages.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReportCatalogEntry(BaseModel):
    report_key: str = Field(..., examples=["daily.production_report"])
    title: str
    category: str = Field(..., examples=["daily"])
    phase: str = Field(..., examples=["P1"])


class ReportCatalog(BaseModel):
    """Reports the caller may see, grouped client-side by ``category``."""

    reports: list[ReportCatalogEntry] = Field(default_factory=list)
