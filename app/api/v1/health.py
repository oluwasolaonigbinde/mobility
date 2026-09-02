import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.db.session import get_engine
from app.operations.readiness import public_readiness
from app.services.data_lifecycle import check_partition_coverage, is_partitioned

logger = logging.getLogger(__name__)

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
    result = await public_readiness(settings)
    return JSONResponse(
        status_code=status.HTTP_200_OK if result.ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ok" if result.ready else "degraded",
            "components": result.components,
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
        logger.exception("health=partitions outcome=check_failed")
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
