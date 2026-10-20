from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class BudgetPolicyContext:
    campaign_id: UUID
    currency: str
    configured_budget_amount: Decimal | None
    total_billing_spend_amount: Decimal
    # D104: the accepted gross; booked amounts up to it never warn or pause.
    agreed_total_amount: Decimal | None = None


@dataclass(frozen=True, slots=True)
class BudgetPolicyDecision:
    state: str
    policy_id: str | None
    policy_revision: str | None
    policy_source: str | None
    budget_basis: str | None
    billing_spend_amount: Decimal | None
    alert_threshold_amount: Decimal | None
    pause_threshold_amount: Decimal | None
    resume_threshold_amount: Decimal | None
    should_pause: bool
    resume_allowed: bool
    # Optional second alert level; None keeps a two-level (alert/pause) decision.
    urgent_threshold_amount: Decimal | None = None


class BudgetPolicyAdapter(Protocol):
    async def evaluate(self, context: BudgetPolicyContext) -> BudgetPolicyDecision: ...


class FixedBudgetPolicyAdapter:
    """Explicit policy input; synthetic values are accepted only by test-authorized callers."""

    def __init__(
        self,
        *,
        policy_id: str,
        policy_revision: str,
        policy_source: str,
        alert_ratio: Decimal,
        pause_ratio: Decimal,
        resume_ratio: Decimal,
        urgent_ratio: Decimal | None = None,
    ) -> None:
        if policy_source not in {"external_approved", "synthetic_test"}:
            raise ValueError("invalid_budget_policy_source")
        if not (
            Decimal("0") < resume_ratio <= pause_ratio and Decimal("0") < alert_ratio < pause_ratio
        ):
            raise ValueError("invalid_budget_policy_threshold_order")
        if urgent_ratio is not None and not (alert_ratio < urgent_ratio < pause_ratio):
            raise ValueError("invalid_budget_policy_threshold_order")
        self.policy_id = policy_id
        self.policy_revision = policy_revision
        self.policy_source = policy_source
        self.alert_ratio = alert_ratio
        self.urgent_ratio = urgent_ratio
        self.pause_ratio = pause_ratio
        self.resume_ratio = resume_ratio

    async def evaluate(self, context: BudgetPolicyContext) -> BudgetPolicyDecision:
        # D104: only the total budget is enforced.
        if not context.configured_budget_amount:
            raise ValueError("budget_policy_requires_budget")
        budget, spend = context.configured_budget_amount, context.total_billing_spend_amount
        alert = (budget * self.alert_ratio).quantize(Decimal("0.0001"))
        urgent = (
            (budget * self.urgent_ratio).quantize(Decimal("0.0001"))
            if self.urgent_ratio is not None
            else None
        )
        pause = (budget * self.pause_ratio).quantize(Decimal("0.0001"))
        resume = (budget * self.resume_ratio).quantize(Decimal("0.0001"))
        # D104: campaigns are fixed price, so only charges beyond the agreed total warn, and
        # spend equal to the budget is within it.
        state = (
            "within_budget"
            if context.agreed_total_amount is not None and spend <= context.agreed_total_amount
            else "pause_threshold"
            if spend > pause
            else "urgent_threshold"
            if urgent is not None and spend >= urgent
            else "alert_threshold"
            if spend >= alert
            else "within_budget"
        )
        return BudgetPolicyDecision(
            state=state,
            policy_id=self.policy_id,
            policy_revision=self.policy_revision,
            policy_source=self.policy_source,
            budget_basis="total",
            billing_spend_amount=spend,
            alert_threshold_amount=alert,
            pause_threshold_amount=pause,
            resume_threshold_amount=resume,
            should_pause=state == "pause_threshold",
            resume_allowed=spend <= resume,
            urgent_threshold_amount=urgent,
        )


def build_budget_policy_adapter() -> FixedBudgetPolicyAdapter:
    """D92: the client's fixed 80/95/100 rule, with no deployment-policy gate."""
    return FixedBudgetPolicyAdapter(
        policy_id="cardvert-client-budget",
        policy_revision="D92",
        policy_source="external_approved",
        alert_ratio=Decimal("0.80"),
        urgent_ratio=Decimal("0.95"),
        pause_ratio=Decimal("1"),
        resume_ratio=Decimal("1"),
    )
