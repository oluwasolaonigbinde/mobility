"""Read only numeric cohort facts for the authenticated isolated E2E organization."""

import asyncio
import json
import runpy
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


async def main() -> None:
    from app.core.config import get_settings
    from app.models.campaign import Campaign
    from app.models.trip import TripSession

    guard = runpy.run_path(str(Path(__file__).with_name("prepare-account-setup-application.py")))
    settings = guard["validate_isolated_e2e_settings"](get_settings())
    if len(sys.argv) != 2:
        raise RuntimeError("Cohort proof requires the authenticated organization UUID")
    organization_id = UUID(sys.argv[1])
    if str(organization_id) != sys.argv[1].lower():
        raise RuntimeError("Cohort proof requires a canonical organization UUID")
    assert settings.database_url is not None
    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            # Match the unbounded dashboard trip cohort, not a report-period cohort.
            trips, cars = (
                await session.execute(
                    select(
                        func.count(TripSession.id),
                        func.count(func.distinct(TripSession.vehicle_id)),
                    )
                    .select_from(TripSession)
                    .join(Campaign, Campaign.id == TripSession.campaign_id)
                    .where(Campaign.organization_id == organization_id)
                )
            ).one()
            print(json.dumps({"trips": trips, "cars": cars}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
