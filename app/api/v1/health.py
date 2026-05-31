from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.db.session import check_database

router = APIRouter(prefix="/health", tags=["health"])
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def _base_payload(settings: Settings) -> dict[str, str]:
    return {
        "service": settings.app_name,
        "environment": settings.environment,
        "status": "ok",
    }


@router.get("", summary="API liveness check")
async def health(settings: SettingsDependency) -> dict[str, str]:
    return {
        **_base_payload(settings),
        "api_version": "v1",
    }


@router.get("/ready", summary="API readiness check")
async def ready(settings: SettingsDependency) -> JSONResponse:
    if not settings.database_url:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                **_base_payload(settings),
                "database": "not_configured",
            },
        )

    if await check_database(settings):
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                **_base_payload(settings),
                "database": "ok",
            },
        )

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            **_base_payload(settings),
            "status": "degraded",
            "database": "unavailable",
        },
    )
