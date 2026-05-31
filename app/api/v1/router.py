from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.advertiser_organizations import router as advertiser_organizations_router
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.me import router as me_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(me_router)
api_router.include_router(admin_router)
api_router.include_router(advertiser_organizations_router)
api_router.include_router(health_router)
