from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.db.session import check_database, get_engine
from app.services.data_lifecycle import check_partition_coverage, is_partitioned

router = APIRouter(prefix="/health", tags=["Health"])
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


@router.get("/partitions", summary="Location-ping partition coverage check")
async def partitions(settings: SettingsDependency) -> JSONResponse:
    """503 when no partition covers now() + 1 month — the API-side detector
    for the write-outage failure mode (catches a dead worker, which no
    worker-side check can). Deliberately separate from /ready: a partition
    gap a month out must not drop live API traffic."""
    if not settings.database_url:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                **_base_payload(settings),
                "partitions": "not_configured",
            },
        )

    try:
        engine = get_engine(settings)
        async with engine.connect() as connection:
            if not await is_partitioned(connection):
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        **_base_payload(settings),
                        "status": "degraded",
                        "partitions": "not_partitioned",
                        "covered_until": None,
                    },
                )
            covered, upper = await check_partition_coverage(connection)
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                **_base_payload(settings),
                "status": "degraded",
                "partitions": "unavailable",
                "covered_until": None,
            },
        )

    if covered:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                **_base_payload(settings),
                "partitions": "ok",
                "covered_until": upper.isoformat() if upper else None,
            },
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            **_base_payload(settings),
            "status": "degraded",
            "partitions": "uncovered",
            "covered_until": upper.isoformat() if upper else None,
        },
    )
