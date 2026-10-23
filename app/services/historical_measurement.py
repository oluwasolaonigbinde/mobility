"""Read-only reproduction of historical frozen measurement manifests (D71).

S9/D118 retires the measurement issuance workflow; current reports use the
campaign-report renderer. This pure calculation cannot publish or change pay.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.models.measurement import MeasurementRun
from app.services.report_cohorts import economic_ledger_amount

MEASUREMENT_FORMULA_VERSION = "measurement-result-v2"
MEASUREMENT_METHOD_REVISION = "measurement-contract-v2"

# Frozen disclosure wording. Each constant reproduces one clause of
# docs/measurement-methodology.json verbatim so a run stays reproducible from its
# own manifest; tests/test_measurement_methodology.py asserts the equality.
VERIFIED_MOVEMENT_CAVEAT = (
    "Completeness and quality scores describe collection quality; movement does not prove "
    "that a person saw an advert."
)
MODELLED_CONTACTS_UNCERTAINTY = (
    "Model confidence is a diagnostic, not a statistical confidence interval."
)
DENSITY_PARAMETER_SOURCE = (
    "impressions_v1 output over verified vehicle movement and the applicable traffic profile"
)
DENSITY_PARAMETER_CALIBRATION = (
    "Traffic-density parameters are configured operational defaults recorded in a versioned "
    "traffic profile; no independent field calibration or external traffic survey has been "
    "applied."
)
SUPPRESSED_TOTAL_LABEL = "Not enough data"

# A cohort trip only enters the completeness denominator once its session is
# terminal; a trip still running at the period boundary is disclosed separately
# and is not missing evidence.
TERMINAL_COHORT_TRIP_STATUSES = frozenset({"ended", "sealed"})
DENSITY_PROFILE_PROVENANCE_FIELDS = (
    "lineage_id",
    "revision",
    "effective_from",
    "value_fingerprint",
    "traffic_density_per_km",
    "dwell_impressions_per_minute",
)


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        _json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _cohort_completeness(input_manifest: dict[str, Any]) -> dict[str, int]:
    """Freeze the R46 cohort's completeness denominator without reselecting it."""
    cohort = input_manifest.get("cohort") or []
    terminal = len(_qualifying_trip_ids(input_manifest))
    return {
        "cohort_trip_count": len(cohort),
        "denominator_trip_count": terminal,
        "in_progress_trip_count": len(cohort) - terminal,
    }


def _qualifying_trip_ids(input_manifest: dict[str, Any]) -> set[str]:
    """Return only cohort trips that became terminal inside the half-open period."""
    period_end_at = datetime.fromisoformat(input_manifest["period"]["end_at"])
    period_start_at = datetime.fromisoformat(input_manifest["period"]["start_at"])
    return {
        str(trip["trip_session_id"])
        for trip in input_manifest.get("cohort") or []
        if str(trip.get("status", "")) in TERMINAL_COHORT_TRIP_STATUSES
        and trip.get("terminal_at") is not None
        and datetime.fromisoformat(str(trip["terminal_at"])) < period_end_at
        and (
            input_manifest["formula_version"] == "measurement-result-v1"
            or datetime.fromisoformat(str(trip["terminal_at"])) >= period_start_at
        )
    }


def _qualifying_rows(rows: list[dict[str, Any]], trip_ids: set[str]) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("trip_session_id", "")) in trip_ids]


def _metric_completeness(
    cohort: dict[str, int],
    *,
    covered_trip_ids: set[str],
    insufficient_trip_ids: set[str],
    excluded_trip_ids: set[str],
    provenance_available: bool = True,
) -> dict[str, Any]:
    """Apply the one completeness/suppression rule from the methodology contract."""
    covered = len(covered_trip_ids)
    denominator = cohort["denominator_trip_count"]
    return {
        **cohort,
        "covered_trip_count": covered,
        "insufficient_data_trip_count": len(insufficient_trip_ids),
        "excluded_trip_count": len(excluded_trip_ids),
        "complete": denominator > 0 and covered >= denominator,
        "suppressed": covered == 0 or not provenance_available,
    }


def _density_provenance(estimated_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    """Freeze the density parameter, source and calibration beside modelled contacts."""
    profiles: dict[tuple[str, ...], dict[str, str]] = {}
    all_rows_complete = bool(estimated_rows)
    for row in estimated_rows:
        provenance = row.get("provenance")
        profile = (
            provenance.get("traffic_density_profile") if isinstance(provenance, dict) else None
        )
        road_category_method = (
            provenance.get("road_category_method", "") if isinstance(provenance, dict) else ""
        )
        if (
            not isinstance(profile, dict)
            or not profile.get("id")
            or any(not profile.get(field) for field in DENSITY_PROFILE_PROVENANCE_FIELDS)
            or not road_category_method
        ):
            all_rows_complete = False
            continue
        frozen = {"profile_id": str(profile["id"])}
        frozen.update(
            {field: str(profile.get(field, "")) for field in DENSITY_PROFILE_PROVENANCE_FIELDS}
        )
        frozen["road_category_method"] = str(road_category_method)
        profiles[tuple(frozen.values())] = frozen
    return (
        {
            "source": DENSITY_PARAMETER_SOURCE,
            "calibration": DENSITY_PARAMETER_CALIBRATION,
            "profiles": [profiles[key] for key in sorted(profiles)],
        },
        all_rows_complete,
    )


def _trip_ids(rows: list[dict[str, Any]], *statuses: str) -> set[str]:
    return {
        str(row.get("trip_session_id", index))
        for index, row in enumerate(rows)
        if row["status"] in statuses
    }


def calculate_measurement_result(input_manifest: dict[str, Any]) -> dict[str, Any]:
    version = input_manifest["formula_version"]
    if version not in {"measurement-result-v1", "measurement-result-v2"}:
        raise ValueError("Unsupported measurement formula")
    qualifying_trip_ids = _qualifying_trip_ids(input_manifest)
    analytics = _qualifying_rows(input_manifest["sources"]["trip_analytics"], qualifying_trip_ids)
    impressions = _qualifying_rows(
        input_manifest["sources"]["impression_estimates"], qualifying_trip_ids
    )
    payouts = _qualifying_rows(
        input_manifest["sources"]["payout_calculations"], qualifying_trip_ids
    )
    measured_rows = [row for row in analytics if row["status"] == "computed"]
    estimated_rows = [row for row in impressions if row["status"] == "estimated"]
    calculated_rows = [row for row in payouts if row["status"] == "calculated"]
    costs: dict[str, Decimal] = {}
    if version == "measurement-result-v1":
        for row in calculated_rows:
            costs[row["currency"]] = costs.get(row["currency"], Decimal("0")) + _decimal(
                row["final_payout"]
            )
    else:
        ledger = _qualifying_rows(
            input_manifest["sources"]["earnings_ledger_entries"], qualifying_trip_ids
        )
        for payout in calculated_rows:
            if not any(row["payout_calculation_id"] == payout["id"] for row in ledger):
                raise ValueError("Calculated trip lacks frozen ledger authority")
            costs.setdefault(payout["currency"], Decimal("0.00"))
        for row in ledger:
            amount = economic_ledger_amount(
                row["entry_type"], row["status"], Decimal(row["amount"])
            )
            costs[row["currency"]] = costs.get(row["currency"], Decimal("0.00")) + amount
    cohort = _cohort_completeness(input_manifest)
    density_provenance, density_provenance_complete = _density_provenance(estimated_rows)
    movement_completeness = _metric_completeness(
        cohort,
        covered_trip_ids=_trip_ids(analytics, "computed"),
        insufficient_trip_ids=_trip_ids(analytics, "insufficient_data"),
        excluded_trip_ids=_trip_ids(analytics, "blocked"),
    )
    contacts_completeness = _metric_completeness(
        cohort,
        covered_trip_ids=_trip_ids(impressions, "estimated"),
        insufficient_trip_ids=_trip_ids(impressions, "insufficient_data"),
        excluded_trip_ids=_trip_ids(impressions, "excluded"),
        provenance_available=density_provenance_complete,
    )
    cost_completeness = _metric_completeness(
        cohort,
        covered_trip_ids=_trip_ids(payouts, "calculated"),
        insufficient_trip_ids=_trip_ids(payouts, "insufficient_data"),
        excluded_trip_ids=_trip_ids(payouts, "blocked"),
    )
    metrics: list[dict[str, Any]] = [
        {
            "id": "verified_vehicle_movement",
            "label": "Verified vehicle movement",
            "class": "measured_operational_fact",
            "trip_count": len({row["trip_session_id"] for row in measured_rows}),
            "distance_m": None
            if movement_completeness["suppressed"]
            else str(sum((_decimal(row["distance_m"]) for row in measured_rows), Decimal(0))),
            "active_tracking_seconds": None
            if movement_completeness["suppressed"]
            else sum(int(row["active_tracking_seconds"]) for row in measured_rows),
            "completeness": movement_completeness,
            "uncertainty": VERIFIED_MOVEMENT_CAVEAT,
        },
        {
            "id": "modelled_potential_contacts",
            "label": "Modelled potential contacts",
            "class": "modelled_measure",
            "value": None
            if contacts_completeness["suppressed"]
            else str(
                sum(
                    (_decimal(row["estimated_impressions"]) for row in estimated_rows),
                    Decimal(0),
                )
            ),
            "formula_versions": sorted({row["formula_version"] for row in estimated_rows}),
            "completeness": contacts_completeness,
            "density_provenance": density_provenance,
            "uncertainty": MODELLED_CONTACTS_UNCERTAINTY,
        },
        {
            "id": "driver_campaign_cost",
            "label": "Driver campaign cost",
            "class": "measured_financial_fact",
            "totals_by_currency": [
                {"currency": currency, "value": str(costs[currency])} for currency in sorted(costs)
            ],
            "completeness": cost_completeness,
        },
    ]
    result: dict[str, Any] = {
        "schema_version": "measurement-result-v1",
        "title": "Campaign Performance Analysis",
        "formula_version": input_manifest["formula_version"],
        "method_revision": input_manifest["method_revision"],
        "period": input_manifest["period"],
        "metrics": metrics,
        "proof_manifest_sha256": input_manifest["proof_manifest_sha256"],
    }
    return result


def measurement_run_reproducible(run: MeasurementRun) -> bool:
    if canonical_sha256(run.input_manifest) != run.input_manifest_sha256:
        return False
    if canonical_sha256(run.proof_manifest) != run.proof_manifest_sha256:
        return False
    if canonical_sha256(run.report_snapshot) != run.report_snapshot_sha256:
        return False
    disclosure_authority = run.input_manifest.get("disclosure_authority")
    if not isinstance(disclosure_authority, dict) or (
        disclosure_authority.get("report_snapshot_sha256") != run.report_snapshot_sha256
    ):
        return False
    try:
        reproduced = calculate_measurement_result(run.input_manifest)
    except (AttributeError, KeyError, TypeError, ValueError, ArithmeticError):
        # A manifest that no longer satisfies the current frozen contract is not
        # reproducible; the caller's fail-closed state must not become a 500.
        return False
    return (
        canonical_sha256(reproduced) == run.result_manifest_sha256
        and reproduced == run.result_manifest
    )
