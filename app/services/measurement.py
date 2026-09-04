from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import LOCAL_ENVIRONMENTS, Settings
from app.core.errors import AppError
from app.models.campaign import Campaign, CampaignCreative
from app.models.campaign_assignment import (
    CampaignActivationEvent,
    CampaignActivationEventType,
    CampaignAssignment,
)
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.exposure_score import ExposureScore
from app.models.installation_evidence import InstallationEvidenceSubmission
from app.models.measurement import MeasurementRun, MeasurementRunProofBinding
from app.models.organization import OrganizationMembership
from app.models.user import User, UserRole, UserStatus
from app.schemas.measurement import MeasurementRunCreate, MeasurementRunRead
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.campaign_assignments import activation_snapshot_digest
from app.services.disclosure import (
    _approved_reference,
    lock_trip_disclosure_snapshot,
    trip_cohort_meets_disclosure_floor,
)
from app.services.heatmaps import (
    AUTHORITATIVE_AUDIENCE_CELL_FORMULA_VERSION,
    authoritative_audience_trip_cell_counts,
)
from app.services.report_cohorts import select_report_cohort
from app.services.reports import build_dynamic_campaign_report

MEASUREMENT_FORMULA_VERSION = "measurement-result-v1"
MEASUREMENT_METHOD_REVISION = "measurement-contract-v1"

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
SUPPRESSED_TOTAL_LABEL = "Omitted - insufficient frozen evidence"
ROI_METHOD_LIMITATIONS = (
    "Return on investment is computed from advertiser-supplied conversion and revenue inputs "
    "that Cardvert does not verify. It is not causal lift, incremental value, verified "
    "exposure, or attribution of a person to an advert, and modelled potential contacts are "
    "never one of its inputs."
)

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
    period_end_at = datetime.fromisoformat(input_manifest["period"]["end_at"])
    terminal = sum(
        1
        for trip in cohort
        if str(trip.get("status", "")) in TERMINAL_COHORT_TRIP_STATUSES
        and trip.get("terminal_at") is not None
        and datetime.fromisoformat(str(trip["terminal_at"])) < period_end_at
    )
    return {
        "cohort_trip_count": len(cohort),
        "denominator_trip_count": terminal,
        "in_progress_trip_count": len(cohort) - terminal,
    }


def _qualifying_trip_ids(input_manifest: dict[str, Any]) -> set[str]:
    """Return only cohort trips that became terminal inside the half-open period."""
    period_end_at = datetime.fromisoformat(input_manifest["period"]["end_at"])
    return {
        str(trip["trip_session_id"])
        for trip in input_manifest.get("cohort") or []
        if str(trip.get("status", "")) in TERMINAL_COHORT_TRIP_STATUSES
        and trip.get("terminal_at") is not None
        and datetime.fromisoformat(str(trip["terminal_at"])) < period_end_at
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
        road_category_method = provenance.get("road_category_method", "")
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
    qualifying_trip_ids = _qualifying_trip_ids(input_manifest)
    analytics = _qualifying_rows(
        input_manifest["sources"]["trip_analytics"], qualifying_trip_ids
    )
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
    for row in calculated_rows:
        costs[row["currency"]] = costs.get(row["currency"], Decimal("0")) + _decimal(
            row["final_payout"]
        )
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
        "mode": input_manifest["mode"],
        "formula_version": input_manifest["formula_version"],
        "method_revision": input_manifest["method_revision"],
        "period": input_manifest["period"],
        "metrics": metrics,
        "proof_manifest_sha256": input_manifest["proof_manifest_sha256"],
        "roi": None,
        "roi_gate": {"decision": "OMIT"},
    }
    roi = input_manifest.get("roi")
    if input_manifest["mode"] == "roi_enabled" and roi is not None:
        revenue = _decimal(roi["attributed_revenue"])
        cost = _decimal(roi["approved_cost_basis"])
        ratio = (revenue - cost) / cost
        method = roi["method"]
        result["roi"] = {
            "label": "Return on investment",
            "class": "conditional_financial_measure",
            "ratio": str(ratio),
            "percent": str(ratio * 100),
            "currency": roi["currency"],
            "method_revision": method["revision"],
            "method": {
                "approval_reference": method["approval_reference"],
                "attribution_rule": method["attribution_rule"],
                "attribution_window": method["attribution_window"],
                "cost_basis": method["cost_basis"],
                "exclusions": method["exclusions"],
                "corrections": method["corrections"],
                "late_data": method["late_data"],
                "limitations": ROI_METHOD_LIMITATIONS,
            },
            "provenance": {
                "conversion_provenance": roi["conversion_provenance"],
                "revenue_provenance": roi["revenue_provenance"],
                "reporting_cutoff": roi["reporting_cutoff"],
                "synthetic": bool(roi["synthetic"]),
            },
        }
        result["roi_gate"] = {"decision": "INCLUDE", "test_only": input_manifest["test_only"]}
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


def _validate_issuance(payload: MeasurementRunCreate, settings: Settings) -> None:
    local = settings.environment.lower() in LOCAL_ENVIRONMENTS
    if payload.test_only:
        if not local:
            raise AppError(
                "SYNTHETIC_MEASUREMENT_RUN_FORBIDDEN",
                "Synthetic measurement runs are limited to local and test environments",
                status_code=status.HTTP_409_CONFLICT,
            )
    elif not settings.measurement_live_issuance_authorized or not _approved_reference(
        settings.measurement_report_method_reference
    ):
        raise AppError(
            "MEASUREMENT_LIVE_ISSUANCE_BLOCKED",
            "Live measurement issuance is not authorized for this deployment",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if payload.mode == "roi_enabled":
        roi = payload.roi
        if roi is None:
            raise AppError(
                "ROI_PREREQUISITES_REQUIRED",
                "ROI-enabled runs require every approved input and method prerequisite",
                status_code=status.HTTP_409_CONFLICT,
            )
        if payload.test_only:
            if not roi.synthetic or roi.method.approval_reference != "SYNTHETIC_TEST_ONLY":
                raise AppError(
                    "ROI_PREREQUISITES_REQUIRED",
                    "Synthetic ROI runs require explicitly synthetic inputs and approval",
                    status_code=status.HTTP_409_CONFLICT,
                )
        elif (
            roi.synthetic
            or not _approved_reference(settings.measurement_roi_method_reference)
            or roi.method.approval_reference != settings.measurement_roi_method_reference
        ):
            raise AppError(
                "ROI_PREREQUISITES_REQUIRED",
                "ROI-enabled runs require the configured approved method reference",
                status_code=status.HTTP_409_CONFLICT,
            )


async def _lock_request(session: AsyncSession, actor_id: UUID, request_id: UUID) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    digest = hashlib.sha256(f"measurement-run:{actor_id}:{request_id}".encode()).digest()[:8]
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(digest, "big", signed=True)},
    )


async def _audience_exposure_authority(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    trip_ids: list[UUID],
    resolution_m: int,
    window_start_at: datetime,
    window_end_at: datetime,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if session.get_bind().dialect.name == "postgresql" and trip_ids:
        zone_ids = list(
            (
                await session.scalars(
                    select(CampaignZone.id)
                    .where(
                        CampaignZone.campaign_id == campaign_id,
                        CampaignZone.zone_type == CampaignZoneType.TARGET,
                    )
                    .order_by(CampaignZone.id)
                )
            ).all()
        )
        for zone_id in zone_ids:
            zone_rows = await authoritative_audience_trip_cell_counts(
                session,
                trip_ids=trip_ids,
                zone_id=zone_id,
                resolution_m=resolution_m,
                window_start_at=window_start_at,
                window_end_at=window_end_at,
            )
            rows.extend(
                {
                    "zone_id": str(zone_id),
                    "grid_x": int(row["grid_x"]),
                    "grid_y": int(row["grid_y"]),
                    "trip_session_id": str(row["trip_session_id"]),
                    "vehicle_id": str(row["vehicle_id"]),
                    "cell_ping_count": int(row["cell_ping_count"]),
                    "total_ping_count": int(row["total_ping_count"]),
                    "recorded_days": [
                        day.isoformat() for day in row["recorded_days"]
                    ],
                }
                for row in zone_rows
            )
    return {
        "schema_version": "audience-exposure-authority-v1",
        "formula_version": AUTHORITATIVE_AUDIENCE_CELL_FORMULA_VERSION,
        "resolution_m": resolution_m,
        "window_start_at": _json_value(window_start_at),
        "window_end_at": _json_value(window_end_at),
        "rows": rows,
    }


async def _proof_manifest(
    session: AsyncSession, *, campaign_id: UUID, assignment_ids: set[UUID]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not assignment_ids:
        raise AppError(
            "MEASUREMENT_INPUTS_REQUIRED",
            "A measurement run requires at least one measured campaign assignment",
            status_code=status.HTTP_409_CONFLICT,
        )
    bindings: list[dict[str, Any]] = []
    for assignment_id in sorted(assignment_ids, key=str):
        assignment = await session.get(CampaignAssignment, assignment_id)
        event = await session.scalar(
            select(CampaignActivationEvent)
            .where(
                CampaignActivationEvent.assignment_id == assignment_id,
                CampaignActivationEvent.event_type == CampaignActivationEventType.ACTIVATED.value,
            )
            .order_by(CampaignActivationEvent.occurred_at.desc(), CampaignActivationEvent.id.desc())
            .limit(1)
        )
        if assignment is None or assignment.campaign_id != campaign_id or event is None:
            raise AppError(
                "MEASUREMENT_PROOF_REQUIRED",
                "Every measured assignment requires immutable activation proof",
                status_code=status.HTTP_409_CONFLICT,
            )
        snapshot = event.event_metadata.get("activation_snapshot")
        snapshot_sha = event.event_metadata.get("activation_snapshot_sha256")
        if (
            not isinstance(snapshot, dict)
            or not isinstance(snapshot_sha, str)
            or activation_snapshot_digest(snapshot) != snapshot_sha
            or snapshot.get("assignment_id") != str(assignment.id)
            or snapshot.get("campaign_id") != str(campaign_id)
            or snapshot.get("offer_terms_sha256") != assignment.offer_terms_sha256
        ):
            raise AppError(
                "MEASUREMENT_PROOF_REQUIRED",
                "Every measured assignment requires a valid activation snapshot",
                status_code=status.HTTP_409_CONFLICT,
            )
        try:
            creative_id = UUID(str(snapshot["creative_id"]))
            evidence_id = UUID(str(snapshot["installation_evidence_submission_id"]))
        except (KeyError, ValueError) as exc:
            raise AppError(
                "MEASUREMENT_PROOF_REQUIRED",
                "Activation proof must bind creative and installation evidence",
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        creative = await session.get(CampaignCreative, creative_id)
        evidence = await session.get(InstallationEvidenceSubmission, evidence_id)
        activated_at = event.occurred_at
        if (
            creative is None
            or creative.campaign_id != campaign_id
            or evidence is None
            or evidence.assignment_id != assignment_id
            or evidence.campaign_id != campaign_id
            or snapshot.get("installation_evidence_revision") != evidence.revision
            or evidence.reviewed_at is None
            or evidence.approved_until is None
            or evidence.reviewed_at > activated_at
            or evidence.approved_until <= activated_at
        ):
            raise AppError(
                "MEASUREMENT_PROOF_REQUIRED",
                "Approved installation evidence must cover the activation proof",
                status_code=status.HTTP_409_CONFLICT,
            )
        item = {
            "assignment_id": str(assignment_id),
            "activation_event_id": str(event.id),
            "creative_id": str(creative_id),
            "installation_evidence_submission_id": str(evidence_id),
            "installation_evidence_revision": evidence.revision,
            "activation_snapshot_sha256": snapshot_sha,
        }
        item["binding_fingerprint"] = canonical_sha256(item)
        bindings.append(item)
    manifest = {"schema_version": "measurement-proof-manifest-v1", "bindings": bindings}
    return manifest, bindings


async def issue_measurement_run(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    payload: MeasurementRunCreate,
    settings: Settings,
) -> MeasurementRun:
    await require_active_admin(session, actor_user_id)
    _validate_issuance(payload, settings)
    await _lock_request(session, actor_user_id, payload.client_request_id)
    request_body = payload.model_dump(mode="json", exclude={"client_request_id"})
    request_fingerprint = canonical_sha256(request_body)
    replay = await session.scalar(
        select(MeasurementRun).where(
            MeasurementRun.created_by_user_id == actor_user_id,
            MeasurementRun.client_request_id == payload.client_request_id,
        )
    )
    if replay is not None:
        if replay.request_fingerprint != request_fingerprint:
            raise AppError(
                "MEASUREMENT_REQUEST_REUSE_CONFLICT",
                "The client request id was already used with different measurement inputs",
                status_code=status.HTTP_409_CONFLICT,
            )
        return replay
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == payload.campaign_id).with_for_update()
    )
    if campaign is None:
        raise AppError(
            "CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=status.HTTP_404_NOT_FOUND
        )
    await lock_trip_disclosure_snapshot(
        session,
        tenant_id=campaign.organization_id,
        campaign_id=campaign.id,
    )
    cohort = await select_report_cohort(
        session,
        campaign_id=campaign.id,
        start_at=payload.period_start_at,
        end_at=payload.period_end_at,
        settings=settings,
    )
    analytics_rows = list(cohort.analytics)
    impression_rows = list(cohort.impressions)
    payout_rows = list(cohort.payouts)
    assignment_ids = {
        row.assignment_id for row in [*analytics_rows, *impression_rows, *payout_rows]
    }
    proof_manifest, binding_rows = await _proof_manifest(
        session, campaign_id=campaign.id, assignment_ids=assignment_ids
    )
    proof_sha = canonical_sha256(proof_manifest)
    method_revision = (
        MEASUREMENT_METHOD_REVISION
        if payload.test_only
        else settings.measurement_report_method_reference
    )
    measured_trip_ids = sorted(
        {
            row.trip_session_id
            for row in analytics_rows
            if row.status == "computed"
        },
        key=str,
    )
    audience_exposure_authority = await _audience_exposure_authority(
        session,
        campaign_id=campaign.id,
        trip_ids=measured_trip_ids,
        resolution_m=settings.privacy_min_resolution_m,
        window_start_at=payload.period_start_at,
        window_end_at=payload.period_end_at,
    )

    def frozen_source(values: dict[str, Any]) -> dict[str, Any]:
        frozen = _json_value(values)
        frozen["source_fingerprint"] = canonical_sha256(frozen)
        return frozen

    def frozen_trip(values: dict[str, Any]) -> dict[str, Any]:
        frozen = _json_value(values)
        frozen["trip_fingerprint"] = canonical_sha256(frozen)
        return frozen

    analytics_sources = [
        frozen_source(
            {
                "id": row.id,
                "trip_session_id": row.trip_session_id,
                "assignment_id": row.assignment_id,
                "vehicle_id": row.vehicle_id,
                "status": row.status,
                "formula_version": row.formula_version,
                "started_at": row.started_at,
                "ended_at": row.ended_at,
                "distance_m": row.distance_m,
                "target_zone_distance_m": row.target_zone_distance_m,
                "bonus_zone_distance_m": row.bonus_zone_distance_m,
                "exclusion_zone_distance_m": row.exclusion_zone_distance_m,
                "active_tracking_seconds": row.active_tracking_seconds,
                "quality_score": row.quality_score,
                "computed_at": row.computed_at,
                "provenance": row.analytics_metadata,
            }
        )
        for row in analytics_rows
    ]
    impression_sources = [
        frozen_source(
            {
                "id": row.id,
                "trip_session_id": row.trip_session_id,
                "assignment_id": row.assignment_id,
                "vehicle_id": row.vehicle_id,
                "status": row.status,
                "formula_version": row.formula_version,
                "traffic_density_profile_id": row.traffic_density_profile_id,
                "estimated_impressions": row.estimated_impressions,
                "confidence_score": row.confidence_score,
                "estimated_at": row.estimated_at,
                "is_authoritative": row.is_authoritative,
                "provenance": row.estimate_metadata,
            }
        )
        for row in impression_rows
    ]
    payout_sources = [
        frozen_source(
            {
                "id": row.id,
                "trip_session_id": row.trip_session_id,
                "assignment_id": row.assignment_id,
                "vehicle_id": row.vehicle_id,
                "status": row.status,
                "formula_version": row.formula_version,
                "payout_rule_id": row.payout_rule_id,
                "currency": row.currency,
                "final_payout": row.final_payout,
                "gross_payout": row.gross_payout,
                "calculated_at": row.calculated_at,
                "inputs_fingerprint": row.inputs_fingerprint,
                "provenance": row.payout_metadata,
            }
        )
        for row in payout_rows
    ]
    sources_by_trip: dict[str, dict[str, list[dict[str, str]]]] = {
        str(trip.id): {
            "trip_analytics": [],
            "impression_estimates": [],
            "payout_calculations": [],
        }
        for trip in cohort.trips
    }
    for source_name, rows in (
        ("trip_analytics", analytics_sources),
        ("impression_estimates", impression_sources),
        ("payout_calculations", payout_sources),
    ):
        for row in rows:
            sources_by_trip[row["trip_session_id"]][source_name].append(
                {"id": row["id"], "fingerprint": row["source_fingerprint"]}
            )
    cohort_manifest = [
        frozen_trip(
            {
                "trip_session_id": trip.id,
                "started_at": trip.started_at,
                "status": str(trip.status),
                "terminal_at": trip.ended_at,
                "sources": sources_by_trip[str(trip.id)],
            }
        )
        for trip in cohort.trips
    ]
    input_manifest: dict[str, Any] = {
        "schema_version": "measurement-input-manifest-v1",
        "campaign_id": str(campaign.id),
        "organization_id": str(campaign.organization_id),
        "mode": payload.mode.value,
        "test_only": payload.test_only,
        "formula_version": MEASUREMENT_FORMULA_VERSION,
        "method_revision": method_revision,
        "period": {
            "start_at": _json_value(payload.period_start_at),
            "end_at": _json_value(payload.period_end_at),
        },
        "proof_manifest_sha256": proof_sha,
        "audience_exposure_authority": audience_exposure_authority,
        "cohort": cohort_manifest,
        "sources": {
            "trip_analytics": analytics_sources,
            "impression_estimates": impression_sources,
            "payout_calculations": payout_sources,
        },
        "roi": _json_value(payload.roi.model_dump()) if payload.roi is not None else None,
    }
    result_manifest = calculate_measurement_result(input_manifest)
    report_user_id = await session.scalar(
        select(OrganizationMembership.user_id)
        .join(User, User.id == OrganizationMembership.user_id)
        .where(
            OrganizationMembership.organization_id == campaign.organization_id,
            OrganizationMembership.status == "active",
            User.role == UserRole.ADVERTISER.value,
            User.status == UserStatus.ACTIVE.value,
        )
        .order_by(OrganizationMembership.created_at, OrganizationMembership.id)
        .limit(1)
    )
    if report_user_id is None:
        raise AppError(
            "ADVERTISER_ORGANIZATION_NOT_FOUND",
            "An active advertiser is required to freeze the campaign report",
            status_code=status.HTTP_409_CONFLICT,
        )
    report = await build_dynamic_campaign_report(
        session,
        user_id=report_user_id,
        campaign_id=campaign.id,
        start_at=payload.period_start_at,
        end_at=payload.period_end_at,
        settings=settings.model_copy(update={"privacy_disclosure_synthetic_test_mode": True}),
        cohort=cohort,
    )
    report_snapshot = report.model_dump(
        mode="json",
        exclude={
            "measurement_run",
            "measurement_result",
            "exposure_score",
            "high_exposure_zone_insights",
        },
    )
    latest = await session.scalar(
        select(MeasurementRun)
        .where(
            MeasurementRun.campaign_id == campaign.id,
            MeasurementRun.period_start_at == payload.period_start_at,
            MeasurementRun.period_end_at == payload.period_end_at,
            ~MeasurementRun.id.in_(
                select(MeasurementRun.reissue_of_run_id).where(
                    MeasurementRun.reissue_of_run_id.is_not(None)
                )
            ),
        )
        .order_by(MeasurementRun.created_at.desc(), MeasurementRun.id.desc())
        .limit(1)
    )
    report_sha = canonical_sha256(report_snapshot)
    disclosure_authority = await trip_cohort_meets_disclosure_floor(
        session,
        tenant_id=campaign.organization_id,
        campaign_id=campaign.id,
        start_at=payload.period_start_at,
        end_at=payload.period_end_at,
        route_id="advertiser.campaign.report",
        settings=settings,
        return_manifest=True,
    )
    assert isinstance(disclosure_authority, dict)
    daily_disclosure_authority = await trip_cohort_meets_disclosure_floor(
        session,
        tenant_id=campaign.organization_id,
        campaign_id=campaign.id,
        start_at=payload.period_start_at,
        end_at=payload.period_end_at,
        route_id="advertiser.campaign.daily_metrics",
        settings=settings,
        return_manifest=True,
    )
    if isinstance(daily_disclosure_authority, dict):
        disclosure_authority["passed"] = bool(
            disclosure_authority["passed"] and daily_disclosure_authority["passed"]
        )
        disclosure_authority["contributions"].update(
            {
                f"daily:{metric}": values
                for metric, values in daily_disclosure_authority["contributions"].items()
            }
        )
    else:
        disclosure_authority["passed"] = False
    measurement_contributions: dict[str, dict[str, Decimal]] = {}

    def add_measurement(metric: str, vehicle_id: UUID, value: Any) -> None:
        amount = Decimal(str(value or 0))
        if amount > 0:
            by_vehicle = measurement_contributions.setdefault(metric, {})
            key = str(vehicle_id)
            by_vehicle[key] = by_vehicle.get(key, Decimal("0")) + amount

    for row in analytics_rows:
        if row.status != "computed":
            continue
        add_measurement("measurement:analytics:trip_count", row.vehicle_id, 1)
        add_measurement("measurement:analytics:distance_m", row.vehicle_id, row.distance_m)
        add_measurement(
            "measurement:analytics:active_tracking_seconds",
            row.vehicle_id,
            row.active_tracking_seconds,
        )
    for row in impression_rows:
        if row.status == "estimated":
            add_measurement(
                "measurement:estimated_impressions",
                row.vehicle_id,
                row.estimated_impressions,
            )
    for row in payout_rows:
        if row.status == "calculated":
            add_measurement(
                f"measurement:final_payout:{row.currency}",
                row.vehicle_id,
                row.final_payout,
            )
    disclosure_authority["contributions"].update(
        {
            metric: {vehicle_id: str(value) for vehicle_id, value in values.items()}
            for metric, values in measurement_contributions.items()
        }
    )
    input_manifest["disclosure_authority"] = {
        **disclosure_authority,
        "schema_version": "frozen-report-disclosure-v1",
        "route_id": "advertiser.campaign.report",
        "report_snapshot_sha256": report_sha,
    }
    input_sha = canonical_sha256(input_manifest)
    result_sha = canonical_sha256(result_manifest)
    run = MeasurementRun(
        organization_id=campaign.organization_id,
        campaign_id=campaign.id,
        created_by_user_id=actor_user_id,
        client_request_id=payload.client_request_id,
        request_fingerprint=request_fingerprint,
        mode=payload.mode.value,
        test_only=payload.test_only,
        formula_version=MEASUREMENT_FORMULA_VERSION,
        method_revision=method_revision,
        roi_method_revision=(payload.roi.method.revision if payload.roi is not None else None),
        period_start_at=payload.period_start_at,
        period_end_at=payload.period_end_at,
        input_manifest=input_manifest,
        input_manifest_sha256=input_sha,
        result_manifest=result_manifest,
        result_manifest_sha256=result_sha,
        proof_manifest=proof_manifest,
        proof_manifest_sha256=proof_sha,
        report_snapshot=report_snapshot,
        report_snapshot_sha256=report_sha,
        reissue_of_run_id=latest.id if latest is not None else None,
    )
    session.add(run)
    await session.flush()
    for item in binding_rows:
        session.add(
            MeasurementRunProofBinding(
                measurement_run_id=run.id,
                assignment_id=UUID(item["assignment_id"]),
                activation_event_id=UUID(item["activation_event_id"]),
                creative_id=UUID(item["creative_id"]),
                installation_evidence_submission_id=UUID(
                    item["installation_evidence_submission_id"]
                ),
                activation_snapshot_sha256=item["activation_snapshot_sha256"],
                binding_fingerprint=item["binding_fingerprint"],
            )
        )
    await session.flush()
    from app.services.exposure_scores import issue_exposure_score_for_run

    await issue_exposure_score_for_run(session, run)
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="measurement_run.issued",
        entity_type="measurement_run",
        entity_id=str(run.id),
        metadata={
            "campaign_id": str(campaign.id),
            "mode": run.mode,
            "test_only": run.test_only,
            "reissue_of_run_id": str(run.reissue_of_run_id) if run.reissue_of_run_id else None,
            "input_manifest_sha256": run.input_manifest_sha256,
            "result_manifest_sha256": run.result_manifest_sha256,
            "proof_manifest_sha256": run.proof_manifest_sha256,
        },
    )
    return run


async def measurement_run_read(session: AsyncSession, run: MeasurementRun) -> MeasurementRunRead:
    from app.services.exposure_scores import exposure_score_read

    bindings = list(
        (
            await session.scalars(
                select(MeasurementRunProofBinding)
                .where(MeasurementRunProofBinding.measurement_run_id == run.id)
                .order_by(MeasurementRunProofBinding.assignment_id)
            )
        ).all()
    )
    score = await session.scalar(
        select(ExposureScore)
        .where(ExposureScore.measurement_run_id == run.id)
        .order_by(ExposureScore.created_at.desc(), ExposureScore.id.desc())
        .limit(1)
    )
    return MeasurementRunRead(
        id=run.id,
        organization_id=run.organization_id,
        campaign_id=run.campaign_id,
        created_by_user_id=run.created_by_user_id,
        client_request_id=run.client_request_id,
        mode=run.mode,
        test_only=run.test_only,
        formula_version=run.formula_version,
        method_revision=run.method_revision,
        roi_method_revision=run.roi_method_revision,
        period_start_at=run.period_start_at,
        period_end_at=run.period_end_at,
        input_manifest=run.input_manifest,
        input_manifest_sha256=run.input_manifest_sha256,
        result_manifest=run.result_manifest,
        result_manifest_sha256=run.result_manifest_sha256,
        proof_manifest=run.proof_manifest,
        proof_manifest_sha256=run.proof_manifest_sha256,
        report_snapshot_sha256=run.report_snapshot_sha256,
        reissue_of_run_id=run.reissue_of_run_id,
        created_at=run.created_at,
        proof_bindings=[
            {
                "assignment_id": binding.assignment_id,
                "activation_event_id": binding.activation_event_id,
                "creative_id": binding.creative_id,
                "installation_evidence_submission_id": binding.installation_evidence_submission_id,
                "activation_snapshot_sha256": binding.activation_snapshot_sha256,
                "binding_fingerprint": binding.binding_fingerprint,
            }
            for binding in bindings
        ],
        exposure_score=(await exposure_score_read(session, score) if score is not None else None),
        reproducible=measurement_run_reproducible(run),
    )
