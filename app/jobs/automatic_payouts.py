import logging
from typing import Any

from app.adapters.disbursement import DisabledDisbursementAdapter, DisbursementAdapter
from app.core.config import Settings, get_settings
from app.services.automatic_payouts import run_automatic_payouts, scan_automatic_payout_alerts

logger = logging.getLogger(__name__)


def _adapter(ctx: dict[str, Any]) -> DisbursementAdapter:
    # Same port as the submission sweep: the disabled adapter until W2-01C wires a
    # provider, so a switched-on run records a provider alert and creates nothing.
    return ctx.get("disbursement_adapter") or DisabledDisbursementAdapter()


def _settings(ctx: dict[str, Any]) -> Settings:
    return ctx.get("settings") or get_settings()


async def sweep_automatic_payouts(ctx: dict[str, Any]) -> dict[str, object]:
    """Raise failure/duplicate alerts, then run one automatic payout pass (D39(c))."""
    async with ctx["sessionmaker"]() as session:
        alerts = await scan_automatic_payout_alerts(session)
        await session.commit()
    async with ctx["sessionmaker"]() as session:
        result = await run_automatic_payouts(
            session, settings=_settings(ctx), adapter=_adapter(ctx)
        )
        await session.commit()
    if result.get("outcome") not in {"not_set_up", "paused", "already_ran", "completed"}:
        logger.warning("Automatic payout run did not complete", extra={"result": result})
    return {"alerts_created": alerts, **result}
