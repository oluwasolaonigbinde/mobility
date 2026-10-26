from uuid import UUID

from arq import Retry

from app.services.campaign_report_delivery import REPORT_LEASE_SECONDS, publish_campaign_report


async def generate_campaign_report(ctx, report_id: str):
    result = await publish_campaign_report(
        ctx["sessionmaker"], report_id=UUID(report_id), storage=ctx["storage"]
    )
    if result == "retry":
        raise Retry(defer=REPORT_LEASE_SECONDS)
    return result
