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
    billing_spend_amount: Decimal | None


@dataclass(frozen=True, slots=True)
class BudgetPolicyDecision:
    state: str
    external_gate: str
    policy_version: str | None
    alert_threshold_amount: Decimal | None
    pause_threshold_amount: Decimal | None
    should_pause: bool


class BudgetPolicyAdapter(Protocol):
    async def evaluate(self, context: BudgetPolicyContext) -> BudgetPolicyDecision: ...


class DisabledBudgetPolicyAdapter:
    """Fail-closed policy seam while the owner-controlled rule is missing."""

    async def evaluate(self, context: BudgetPolicyContext) -> BudgetPolicyDecision:
        del context
        return BudgetPolicyDecision(
            state=BLOCKED_BUDGET_POLICY_STATE,
            external_gate=MISSING_BUDGET_POLICY_GATE,
            policy_version=None,
            alert_threshold_amount=None,
            pause_threshold_amount=None,
            should_pause=False,
        )
