from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

MISSING_BUDGET_POLICY_GATE = "EXT-BUDGET-POLICY"
BLOCKED_BUDGET_POLICY_STATE = "blocked_external_policy"


@dataclass(frozen=True, slots=True)
class BudgetPolicyContext:
    campaign_id: UUID
    currency: str
    configured_budget_amount: Decimal | None
    configured_daily_budget_amount: Decimal | None
    total_billing_spend_amount: Decimal
    daily_billing_spend_amount: Decimal


@dataclass(frozen=True, slots=True)
class BudgetPolicyDecision:
    state: str
    external_gate: str | None
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


class BudgetPolicyAdapter(Protocol):
    async def evaluate(self, context: BudgetPolicyContext) -> BudgetPolicyDecision: ...


class DisabledBudgetPolicyAdapter:
    """Fail-closed policy seam while the owner-controlled rule is missing."""

    async def evaluate(self, context: BudgetPolicyContext) -> BudgetPolicyDecision:
        del context
        return BudgetPolicyDecision(
            state=BLOCKED_BUDGET_POLICY_STATE,
            external_gate=MISSING_BUDGET_POLICY_GATE,
            policy_id=None,
            policy_revision=None,
            policy_source=None,
            budget_basis=None,
            billing_spend_amount=None,
            alert_threshold_amount=None,
            pause_threshold_amount=None,
            resume_threshold_amount=None,
            should_pause=False,
            resume_allowed=False,
        )


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
    ) -> None:
        if policy_source not in {"external_approved", "synthetic_test"}:
            raise ValueError("invalid_budget_policy_source")
        if not (Decimal("0") < resume_ratio <= alert_ratio < pause_ratio):
            raise ValueError("invalid_budget_policy_threshold_order")
        self.policy_id = policy_id
        self.policy_revision = policy_revision
        self.policy_source = policy_source
        self.alert_ratio = alert_ratio
        self.pause_ratio = pause_ratio
        self.resume_ratio = resume_ratio

    async def evaluate(self, context: BudgetPolicyContext) -> BudgetPolicyDecision:
        candidates: list[tuple[str, Decimal, Decimal]] = []
        if context.configured_budget_amount is not None:
            candidates.append(
                ("total", context.configured_budget_amount, context.total_billing_spend_amount)
            )
        if context.configured_daily_budget_amount is not None:
            candidates.append(
                (
                    "daily",
                    context.configured_daily_budget_amount,
                    context.daily_billing_spend_amount,
                )
            )
        if not candidates:
            raise ValueError("budget_policy_requires_budget")
        basis, budget, spend = max(
            candidates,
            key=lambda item: item[2] / item[1] if item[1] else Decimal("Infinity"),
        )
        alert = (budget * self.alert_ratio).quantize(Decimal("0.01"))
        pause = (budget * self.pause_ratio).quantize(Decimal("0.01"))
        resume = (budget * self.resume_ratio).quantize(Decimal("0.01"))
        state = (
            "pause_threshold"
            if spend >= pause
            else "alert_threshold"
            if spend >= alert
            else "within_budget"
        )
        return BudgetPolicyDecision(
            state=state,
            external_gate=None,
            policy_id=self.policy_id,
            policy_revision=self.policy_revision,
            policy_source=self.policy_source,
            budget_basis=basis,
            billing_spend_amount=spend,
            alert_threshold_amount=alert,
            pause_threshold_amount=pause,
            resume_threshold_amount=resume,
            should_pause=state == "pause_threshold",
            resume_allowed=spend <= resume,
        )


def build_budget_policy_adapter(settings) -> BudgetPolicyAdapter:
    values = (
        settings.budget_policy_id,
        settings.budget_policy_revision,
        settings.budget_alert_ratio,
        settings.budget_pause_ratio,
        settings.budget_resume_ratio,
    )
    if not settings.budget_policy_external_approved or any(value is None for value in values):
        return DisabledBudgetPolicyAdapter()
    return FixedBudgetPolicyAdapter(
        policy_id=settings.budget_policy_id,
        policy_revision=settings.budget_policy_revision,
        policy_source="external_approved",
        alert_ratio=Decimal(str(settings.budget_alert_ratio)),
        pause_ratio=Decimal(str(settings.budget_pause_ratio)),
        resume_ratio=Decimal(str(settings.budget_resume_ratio)),
    )
