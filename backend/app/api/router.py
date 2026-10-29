from fastapi import APIRouter

from app.api.routes import (
    account,
    accounts,
    auth,
    browsers,
    fingerprints,
    health,
    ip_pool,
    kernels,
    novnc,
    overview,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(overview.router)
api_router.include_router(browsers.router)
api_router.include_router(accounts.router)
api_router.include_router(ip_pool.router)
api_router.include_router(novnc.router)
api_router.include_router(fingerprints.router)
api_router.include_router(kernels.router)
api_router.include_router(account.router)
api_router.include_router(auth.router)
