from fastapi import APIRouter

from app.api.v1 import (
    ai,
    accounting,
    billing,
    fec,
    steering,
    analysis,
    dashboard,
    companies,
    engagements,
    financial_audit,
    fiscal_years,
    frameworks,
    imports,
    internal_audit,
    internal_control,
    ledger,
    management,
    me,
    organizations,
    reporting,
)

api_router = APIRouter()
api_router.include_router(me.router)
api_router.include_router(organizations.router)
api_router.include_router(companies.router)
api_router.include_router(fiscal_years.router)
api_router.include_router(frameworks.router)
api_router.include_router(imports.router)
api_router.include_router(analysis.router)
api_router.include_router(management.router)
api_router.include_router(engagements.router)
api_router.include_router(financial_audit.router)
api_router.include_router(internal_audit.router)
api_router.include_router(ledger.router)
api_router.include_router(internal_control.router)
api_router.include_router(ai.router)
api_router.include_router(reporting.router)
api_router.include_router(dashboard.router)
api_router.include_router(accounting.router)
api_router.include_router(fec.router)
api_router.include_router(steering.router)
api_router.include_router(billing.router)
