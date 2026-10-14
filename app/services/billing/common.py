"""Billing: common domain operations."""

import hashlib
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.billing import (
    ReceiptLifecycleStatus,
)
from app.models.campaign import Campaign

MONEY_QUANTUM = Decimal("0.01")


EXPEDITED_WAIVER_WORDING_VERSION = "advertiser-expedited-v1"


EXPEDITED_WAIVER_WORDING = (
    "I request expedited production and understand refund eligibility ends only when "
    "expedited production actually starts."
)


EXPEDITED_WAIVER_WORDING_HASH = hashlib.sha256(EXPEDITED_WAIVER_WORDING.encode()).hexdigest()


RECEIPT_SEQUENCE = {
    ReceiptLifecycleStatus.OBSERVED: 1,
    ReceiptLifecycleStatus.RECONCILED: 2,
    ReceiptLifecycleStatus.CONFIRMED: 3,
    ReceiptLifecycleStatus.REVERSED: 4,
}


DAILY_RATE_LIABILITY_FORMULA_VERSION = "day-rate-vehicle-days-v1"


LAGOS_TZ = ZoneInfo("Africa/Lagos")


ISSUER_CONTACT_AND_BANK_FIELDS = (
    "company_registration_number",
    "contact_phone",
    "contact_email",
    "bank_name",
    "bank_account_name",
    "bank_account_number",
)


ISSUER_VERIFIED_FACT_FIELDS = ("tax_identification_number", *ISSUER_CONTACT_AND_BANK_FIELDS)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AppError(
            "INVALID_ACCEPTED_AT",
            "accepted_at must include a timezone",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return value.astimezone(UTC)


def _stored_aware_utc(value: datetime) -> datetime:
    """Normalize a trusted DB timestamp to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _money(value: Decimal | str, field: str) -> Decimal:
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise AppError(
            "INVALID_COMMERCIAL_AMOUNT",
            f"{field} must be a decimal amount",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    if not amount.is_finite() or amount < 0 or amount != amount.quantize(MONEY_QUANTUM):
        raise AppError(
            "INVALID_COMMERCIAL_AMOUNT",
            f"{field} must be a non-negative two-decimal amount",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return amount


def _tax_rate(value: Decimal | str) -> Decimal:
    try:
        rate = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise AppError(
            "INVALID_TAX_RATE",
            "tax_rate must be a decimal between 0 and 1",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    if not rate.is_finite() or rate < 0 or rate > 1 or rate != rate.quantize(Decimal("0.000001")):
        raise AppError(
            "INVALID_TAX_RATE",
            "tax_rate must be a decimal between 0 and 1 with at most six decimal places",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return rate


def _line_quantity(item: dict, index: int) -> tuple[int, Decimal] | None:
    """Return (quantity, unit amount) when a line is priced per unit, else None."""
    if "quantity" not in item and "unit_amount" not in item:
        return None
    quantity = item.get("quantity")
    if (
        "unit_amount" not in item
        or isinstance(quantity, bool)
        or not isinstance(quantity, int)
        or quantity < 1
    ):
        raise AppError(
            "INVALID_COMMERCIAL_LINE_ITEM",
            f"Line item {index + 1} needs a whole quantity of at least 1 and a unit amount",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return quantity, _money(item["unit_amount"], f"line_items[{index}].unit_amount")


def _campaign_period(production_scope: dict) -> None:
    """Validate the optional campaign dates an invoice shows as its duration."""
    start = production_scope.get("campaign_start_date")
    end = production_scope.get("campaign_end_date")
    if start is None and end is None:
        return
    try:
        if not isinstance(start, str) or not isinstance(end, str):
            raise ValueError("dates must be strings")
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        # Only YYYY-MM-DD: fromisoformat also takes compact and week forms the invoice can't show.
        if (start_date.isoformat(), end_date.isoformat()) != (start, end):
            raise ValueError("not YYYY-MM-DD")
    except (TypeError, ValueError) as exc:
        raise AppError(
            "INVALID_PRODUCTION_SCOPE",
            "campaign_start_date and campaign_end_date must both be YYYY-MM-DD dates",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    if end_date < start_date:
        raise AppError(
            "INVALID_PRODUCTION_SCOPE",
            "campaign_end_date must not be before campaign_start_date",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


def _canonical_line_items(
    line_items: list[dict],
) -> tuple[list[dict], Decimal, Decimal]:
    if not line_items:
        raise AppError(
            "COMMERCIAL_LINE_ITEMS_REQUIRED",
            "At least one structured quotation line item is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    canonical: list[dict] = []
    net = Decimal("0.00")
    production = Decimal("0.00")
    for index, item in enumerate(line_items):
        if not isinstance(item, dict):
            raise AppError(
                "INVALID_COMMERCIAL_LINE_ITEM",
                "Each quotation line item must be an object",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        code = str(item.get("code", "")).strip()
        description = str(item.get("description", "")).strip()
        kind = str(item.get("kind", "")).strip()
        if not code or not description or kind not in {"media", "production", "other"}:
            raise AppError(
                "INVALID_COMMERCIAL_LINE_ITEM",
                f"Line item {index + 1} requires code, description and a supported kind",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        quantity_value = _line_quantity(item, index)
        if quantity_value is None:
            amount = _money(item.get("amount", ""), f"line_items[{index}].amount")
        else:
            quantity, unit_amount = quantity_value
            amount = unit_amount * quantity
            if "amount" in item and _money(item["amount"], f"line_items[{index}].amount") != amount:
                raise AppError(
                    "INVALID_COMMERCIAL_LINE_ITEM",
                    f"Line item {index + 1} amount must equal quantity times unit amount",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            raise AppError(
                "INVALID_COMMERCIAL_LINE_ITEM",
                f"Line item {index + 1} metadata must be an object",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        line = {
            "code": code,
            "description": description,
            "kind": kind,
            "amount": f"{amount:.2f}",
            "metadata": deepcopy(metadata),
        }
        if quantity_value is not None:
            # Only lines entered with a quantity carry it, so earlier lines keep their shape.
            line["quantity"] = quantity
            line["unit_amount"] = f"{unit_amount:.2f}"
        canonical.append(line)
        net += amount
        if kind == "production":
            production += amount
    return canonical, net, production


async def _campaign(session: AsyncSession, campaign_id: UUID, *, lock: bool = False) -> Campaign:
    statement = select(Campaign).where(Campaign.id == campaign_id)
    if lock:
        statement = statement.with_for_update()
    campaign = (await session.execute(statement)).scalar_one_or_none()
    if campaign is None:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    return campaign
