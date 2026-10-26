from datetime import UTC, datetime
from typing import Any

from app.services.billing.budget import sweep_campaign_budgets


async def sweep_campaign_budget_enforcement(ctx: dict[str, Any]) -> dict[str, int | bool]:
    async with ctx["sessionmaker"]() as session:
        evaluations = await sweep_campaign_budgets(
            session,
        )
        paused = sum(evaluation.pause_applied for evaluation in evaluations)
        alerted = sum(evaluation.alert_applied for evaluation in evaluations)
        await session.commit()
    return {
        "evaluated": len(evaluations),
        "alerted": alerted,
        "paused": paused,
        "policy_configured": True,
        "completed_at_epoch": int(datetime.now(UTC).timestamp()),
    }
