from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.advertiser_organizations import router as advertiser_organizations_router
from app.api.v1.advertiser_reports import router as advertiser_reports_router
from app.api.v1.auth import router as auth_router
from app.api.v1.campaign_assignments import router as campaign_assignments_router
from app.api.v1.campaign_zones import router as campaign_zones_router
from app.api.v1.campaigns import router as campaigns_router
from app.api.v1.driver_profiles import router as driver_profiles_router
from app.api.v1.health import router as health_router
from app.api.v1.heatmaps import router as heatmaps_router
from app.api.v1.impressions import router as impressions_router
from app.api.v1.me import router as me_router
from app.api.v1.payouts import router as payouts_router
from app.api.v1.trip_analytics import router as trip_analytics_router
from app.api.v1.trips import router as trips_router
from app.api.v1.vehicles import router as vehicles_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(me_router)
api_router.include_router(admin_router)
api_router.include_router(advertiser_organizations_router)
api_router.include_router(advertiser_reports_router)
api_router.include_router(campaigns_router)
api_router.include_router(campaign_assignments_router)
api_router.include_router(campaign_zones_router)
api_router.include_router(heatmaps_router)
api_router.include_router(impressions_router)
api_router.include_router(payouts_router)
api_router.include_router(trip_analytics_router)
api_router.include_router(trips_router)
api_router.include_router(driver_profiles_router)
api_router.include_router(vehicles_router)
api_router.include_router(health_router)
