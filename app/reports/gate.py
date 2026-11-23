"""Router-level gate of the public engine routes (ENG-01, 02 §12.4).

The routers are always mounted, so the OpenAPI document and the generated
client are the same in every environment. This dependency decides per request:

* flag off                                  -> 404 ``reports_engine_disabled``
* ENV staging/prod with a configuration that
  would leak a dev default into production  -> 503 ``reports_engine_misconfigured``
                                               with ``details.missing[]``

The rest of the API is unaffected either way.
"""

from __future__ import annotations

from fastapi import status

from app.core.config import Settings, settings
from app.core.exceptions import AppError


class ReportsEngineDisabled(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "reports_engine_disabled"


class ReportsEngineMisconfigured(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "reports_engine_misconfigured"


def configuration_problems(cfg: Settings) -> list[str]:
    """Fail-closed checks of 02 §12.4 that apply to the engine routes.

    Only staging/prod are checked: under ENV=dev the local defaults are intended.
    Later phases add the background, schedule and e-mail checks here.
    """
    if cfg.ENV == "dev":
        return []
    missing: list[str] = []
    if cfg.report_storage_backend == "local":
        missing.append("REPORT_STORAGE_BACKEND (local storage is dev-only)")
    elif not cfg.report_bucket:
        missing.append("GCS_BUCKET_REPORTS or GCS_BUCKET_DOCUMENTS")
    return missing


def require_reports_engine() -> None:
    """FastAPI dependency placed on every public engine router."""
    if not settings.REPORTS_ENGINE_ENABLED:
        raise ReportsEngineDisabled("The reports engine is not enabled for this service.")
    missing = configuration_problems(settings)
    if missing:
        raise ReportsEngineMisconfigured(
            "The reports engine is misconfigured for this environment.",
            details={"missing": missing},
        )
