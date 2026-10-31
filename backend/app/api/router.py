from fastapi import APIRouter

from app.api.routes import (
    accounts,
    audit,
    auth,
    browsers,
    fingerprints,
    health,
    ip_pool,
    kernels,
    novnc,
    overview,
    rbac,
    user,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(overview.router)
api_router.include_router(browsers.router)
# 浏览器账号池：accounts.py（/accounts）
api_router.include_router(accounts.router)
api_router.include_router(ip_pool.router)
api_router.include_router(novnc.router)
api_router.include_router(fingerprints.router)
api_router.include_router(kernels.router)
# 当前登录成员的个人中心：user.py（/user）
api_router.include_router(user.router)
api_router.include_router(auth.router)
api_router.include_router(audit.router)
api_router.include_router(rbac.router)
