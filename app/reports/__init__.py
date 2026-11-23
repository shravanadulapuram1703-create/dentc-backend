"""Reports & Analytics engine (server-side report runs).

The specification is the plan in ``../dentc-frontend/docs/reports/module-plan``
(02_architecture.md is the engine design). Everything here is gated by
``settings.REPORTS_ENGINE_ENABLED``; see :mod:`app.reports.gate`.
"""
