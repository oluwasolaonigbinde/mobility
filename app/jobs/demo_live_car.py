"""REQ-312: five-minute demo live-car refresher; a no-op unless DEMO_LIVE_CAR_REFRESH is set."""

from typing import Any

from app.seeds.live_car import refresh_demo_live_cars


async def refresh_demo_live_cars_job(ctx: dict[str, Any]) -> dict[str, int]:
    from app.services.trips import utc_now

    return await refresh_demo_live_cars(
        ctx["sessionmaker"], settings=ctx["settings"], now=utc_now()
    )
