from datetime import UTC, datetime
from typing import Any

from app.adapters.budget import build_budget_policy_adapter
from app.core.config import get_settings
from app.services.billing import sweep_budget_policy_evaluations


async def sweep_campaign_budget_enforcement(ctx: dict[str, Any]) -> dict[str, int | bool]:
    settings = ctx.get("settings") or get_settings()
    async with ctx["sessionmaker"]() as session:
        evaluations = await sweep_budget_policy_evaluations(
            session,
            adapter=build_budget_policy_adapter(settings),
        )
        paused = sum(evaluation.pause_applied for evaluation in evaluations)
        alerted = sum(evaluation.alert_applied for evaluation in evaluations)
        await session.commit()
    return {
        "evaluated": len(evaluations),
        "alerted": alerted,
        "paused": paused,
        "policy_configured": settings.budget_policy_external_approved,
        "completed_at_epoch": int(datetime.now(UTC).timestamp()),
    }
