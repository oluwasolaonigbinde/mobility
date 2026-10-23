"""S9/D118: issuance tests move to test_req217_reports.

Keep historical math and ledger-cohort coverage.
"""

import asyncio
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from conftest import (
    create_test_payout_rule,
)
from report_fixtures import create_report_fixture
from sqlalchemy import delete, select
from test_advertiser_reports import DAY_1, add_payout_calculation, create_report_graph

from app.models.impression import ImpressionEstimate
from app.models.measurement import MeasurementRun
from app.models.payout import EarningsLedgerEntry
from app.models.trip import TripSession
from app.models.trip_analytics import TripAnalytics
from app.services.historical_measurement import (
    calculate_measurement_result,
    measurement_run_reproducible,
)
from app.services.report_cohorts import select_report_cohort


def test_measurement_result_manifest_is_canonical_json() -> None:
    # A small contract guard against non-JSON Decimal/date values leaking into
    # persisted manifests and making fingerprints database-dependent.

    manifest = {
        "test_only": True,
        "formula_version": "measurement-result-v1",
        "method_revision": "measurement-contract-v1",
        "period": {"start_at": DAY_1.isoformat(), "end_at": (DAY_1 + timedelta(1)).isoformat()},
        "proof_manifest_sha256": "a" * 64,
        "sources": {
            "trip_analytics": [],
            "impression_estimates": [],
            "payout_calculations": [],
        },
    }
    json.dumps(calculate_measurement_result(manifest), sort_keys=True)


def test_postgres_cohort_orders_trips_and_selects_one_replacement_payout(
    postgis_db_sessionmaker, settings
) -> None:
    admin, advertiser, campaign = create_report_fixture(
        postgis_db_sessionmaker, identity_tag="measurement-pg-cohort"
    )
    create_report_graph(
        postgis_db_sessionmaker,
        admin=admin,
        advertiser=advertiser,
        campaign=campaign,
        driver_email="measurement-pg-cohort-second@example.com",
        plate_number="PG-COHORT-2",
        started_at=DAY_1 + timedelta(hours=1),
    )

    async def original_sources():
        async with postgis_db_sessionmaker() as session:
            trip = await session.scalar(
                select(TripSession)
                .where(TripSession.campaign_id == campaign.id)
                .order_by(TripSession.started_at)
            )
            assert trip is not None
            analytics = await session.scalar(
                select(TripAnalytics).where(TripAnalytics.trip_session_id == trip.id)
            )
            estimate = await session.scalar(
                select(ImpressionEstimate).where(ImpressionEstimate.trip_session_id == trip.id)
            )
            ledger = await session.scalar(
                select(EarningsLedgerEntry).where(EarningsLedgerEntry.trip_session_id == trip.id)
            )
            assert analytics is not None and estimate is not None and ledger is not None
            await session.execute(
                delete(EarningsLedgerEntry).where(EarningsLedgerEntry.trip_session_id == trip.id)
            )
            await session.commit()
            return trip, analytics, estimate, ledger.driver_user_id

    trip, analytics, estimate, driver_user_id = asyncio.run(original_sources())
    replacement_rule = create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        currency=campaign.currency,
        status="inactive",
    )
    add_payout_calculation(
        postgis_db_sessionmaker,
        trip=trip,
        analytics=analytics,
        estimate=estimate,
        payout_rule_id=replacement_rule.id,
        driver_user_id=driver_user_id,
        status="calculated",
        final_payout=Decimal("700.00"),
        gross_payout=Decimal("800.00"),
        calculated_at=DAY_1 + timedelta(days=3),
    )

    async def selected():
        async with postgis_db_sessionmaker() as session:
            return await select_report_cohort(
                session,
                campaign_id=campaign.id,
                start_at=DAY_1,
                end_at=DAY_1 + timedelta(days=1),
                settings=settings,
            )

    cohort = asyncio.run(selected())
    assert [row.started_at for row in cohort.trips] == sorted(
        row.started_at for row in cohort.trips
    )
    first_trip_payouts = [row for row in cohort.payouts if row.trip_session_id == trip.id]
    assert len(first_trip_payouts) == 1
    assert first_trip_payouts[0].final_payout == Decimal("700.00")


def _disclosure_manifest(*, cohort_statuses=("sealed", "sealed"), estimated=True):
    """A minimal frozen input manifest exercising the R47 disclosure contract."""
    profile = {
        "id": "00000000-0000-4000-8000-0000000000a1",
        "lineage_id": "00000000-0000-4000-8000-0000000000b1",
        "revision": "2",
        "effective_from": "2026-07-01T00:00:00+00:00",
        "value_fingerprint": "9" * 64,
        "traffic_density_per_km": "180",
        "dwell_impressions_per_minute": "12",
        "road_category_weight": "1.0",
        "morning_weight": "1.0",
        "midday_weight": "1.0",
        "evening_weight": "1.0",
        "night_weight": "0.7",
        "target_zone_weight": "1.0",
        "bonus_zone_weight": "1.25",
        "exclusion_zone_weight": "0.0",
    }
    trip_ids = [
        f"00000000-0000-4000-8000-00000000001{index}" for index in range(len(cohort_statuses))
    ]
    return {
        "test_only": True,
        "formula_version": "measurement-result-v1",
        "method_revision": "measurement-contract-v1",
        "period": {"start_at": DAY_1.isoformat(), "end_at": (DAY_1 + timedelta(1)).isoformat()},
        "proof_manifest_sha256": "a" * 64,
        "cohort": [
            {
                "trip_session_id": trip_id,
                "status": status,
                "terminal_at": (
                    (DAY_1 + timedelta(hours=12)).isoformat()
                    if status in {"ended", "sealed"}
                    else None
                ),
            }
            for trip_id, status in zip(trip_ids, cohort_statuses, strict=True)
        ],
        "sources": {
            "trip_analytics": [
                {
                    "trip_session_id": trip_ids[0],
                    "status": "computed",
                    "distance_m": "1200.00",
                    "active_tracking_seconds": 600,
                }
            ],
            "impression_estimates": (
                [
                    {
                        "trip_session_id": trip_ids[0],
                        "status": "estimated",
                        "formula_version": "impressions_v1",
                        "estimated_impressions": "300.00",
                        "provenance": {
                            "traffic_density_profile": profile,
                            "road_category_method": (
                                "profile_default_weight_no_road_classification_v1"
                            ),
                        },
                    }
                ]
                if estimated
                else [
                    {
                        "trip_session_id": trip_ids[0],
                        "status": "insufficient_data",
                        "formula_version": "impressions_v1",
                        "estimated_impressions": "0.00",
                        "provenance": {},
                    }
                ]
            ),
            "payout_calculations": [
                {
                    "trip_session_id": trip_ids[0],
                    "status": "calculated",
                    "currency": "NGN",
                    "final_payout": "800.00",
                }
            ],
        },
    }


def test_frozen_movement_metric_carries_the_exact_advert_viewing_caveat() -> None:
    # MET-001

    contract = json.loads(
        (Path(__file__).resolve().parents[1] / "docs" / "measurement-methodology.json").read_text()
    )
    expected = next(
        row["uncertainty"]
        for row in contract["metric_hierarchy"]
        if row["id"] == "verified_vehicle_movement"
    )
    metrics = {
        metric["id"]: metric
        for metric in calculate_measurement_result(_disclosure_manifest())["metrics"]
    }

    assert metrics["verified_vehicle_movement"]["uncertainty"] == expected
    # The performance-only claims guard stays undiluted: no ROI wording is added.
    assert "uncertainty" not in metrics["driver_campaign_cost"]


def test_frozen_metrics_disclose_completeness_and_suppress_unsupported_totals() -> None:
    # MET-002

    partial = calculate_measurement_result(
        _disclosure_manifest(cohort_statuses=("sealed", "sealed", "active"))
    )
    metrics = {metric["id"]: metric for metric in partial["metrics"]}
    movement = metrics["verified_vehicle_movement"]["completeness"]

    assert movement["cohort_trip_count"] == 3
    assert movement["denominator_trip_count"] == 2
    assert movement["in_progress_trip_count"] == 1
    assert movement["covered_trip_count"] == 1
    assert movement["complete"] is False
    assert movement["suppressed"] is False
    # A qualified partial value survives; only the denominator disclosure changes.
    assert metrics["verified_vehicle_movement"]["distance_m"] == "1200.00"

    unsupported = calculate_measurement_result(_disclosure_manifest(estimated=False))
    contacts = {metric["id"]: metric for metric in unsupported["metrics"]}[
        "modelled_potential_contacts"
    ]
    assert contacts["completeness"]["insufficient_data_trip_count"] == 1
    assert contacts["completeness"]["suppressed"] is True
    assert contacts["value"] is None


def test_a_cohort_with_no_completed_trip_omits_totals_instead_of_publishing_zero() -> None:
    # The contract's completeness rule: omission never substitutes zero. A cohort whose
    # trips are all still running has no denominator and therefore no publishable total.

    manifest = _disclosure_manifest(cohort_statuses=("active", "active"))
    # Analytics, estimates and payouts only exist once a trip is terminal.
    manifest["sources"] = {source: [] for source in manifest["sources"]}
    metrics = {metric["id"]: metric for metric in calculate_measurement_result(manifest)["metrics"]}
    movement = metrics["verified_vehicle_movement"]

    assert movement["completeness"]["denominator_trip_count"] == 0
    assert movement["completeness"]["in_progress_trip_count"] == 2
    assert movement["completeness"]["complete"] is False
    assert movement["completeness"]["suppressed"] is True
    assert movement["distance_m"] is None
    assert movement["active_tracking_seconds"] is None
    assert metrics["modelled_potential_contacts"]["value"] is None


def test_completeness_excludes_a_trip_that_ends_at_the_frozen_period_boundary() -> None:

    manifest = _disclosure_manifest(cohort_statuses=("sealed",))
    manifest["cohort"][0]["terminal_at"] = manifest["period"]["end_at"]

    metrics = {metric["id"]: metric for metric in calculate_measurement_result(manifest)["metrics"]}
    completeness = metrics["verified_vehicle_movement"]["completeness"]

    assert completeness["denominator_trip_count"] == 0
    assert completeness["in_progress_trip_count"] == 1
    assert completeness["covered_trip_count"] == 0
    assert completeness["suppressed"] is True
    assert metrics["verified_vehicle_movement"]["distance_m"] is None
    assert metrics["modelled_potential_contacts"]["value"] is None


def test_density_provenance_missing_a_required_parameter_suppresses_contacts() -> None:

    manifest = _disclosure_manifest()
    profile = manifest["sources"]["impression_estimates"][0]["provenance"][
        "traffic_density_profile"
    ]
    del profile["traffic_density_per_km"]

    contacts = {
        metric["id"]: metric for metric in calculate_measurement_result(manifest)["metrics"]
    }["modelled_potential_contacts"]

    assert contacts["density_provenance"]["profiles"] == []
    assert contacts["completeness"]["suppressed"] is True
    assert contacts["value"] is None


def test_missing_historical_density_provenance_withholds_contacts_without_crashing() -> None:
    manifest = _disclosure_manifest()
    manifest["sources"]["impression_estimates"][0]["provenance"] = None
    contacts = next(
        metric
        for metric in calculate_measurement_result(manifest)["metrics"]
        if metric["id"] == "modelled_potential_contacts"
    )
    assert contacts["density_provenance"]["profiles"] == []
    assert contacts["completeness"]["suppressed"] is True


def test_mixed_complete_and_incomplete_density_provenance_suppresses_the_total() -> None:

    manifest = _disclosure_manifest()
    second_trip_id = manifest["cohort"][1]["trip_session_id"]
    incomplete = {
        **manifest["sources"]["impression_estimates"][0],
        "trip_session_id": second_trip_id,
        "estimated_impressions": "200.00",
        "provenance": {
            "traffic_density_profile": {
                "id": "00000000-0000-4000-8000-0000000000c1",
            }
        },
    }
    manifest["sources"]["impression_estimates"].append(incomplete)

    contacts = {
        metric["id"]: metric for metric in calculate_measurement_result(manifest)["metrics"]
    }["modelled_potential_contacts"]

    assert contacts["completeness"]["covered_trip_count"] == 2
    assert contacts["completeness"]["suppressed"] is True
    assert contacts["value"] is None
    assert len(contacts["density_provenance"]["profiles"]) == 1


def test_cost_completeness_covers_every_currency_without_suppressing_the_totals() -> None:

    manifest = _disclosure_manifest(cohort_statuses=("sealed", "sealed"))
    manifest["sources"]["payout_calculations"].append(
        {
            "trip_session_id": manifest["cohort"][1]["trip_session_id"],
            "status": "calculated",
            "currency": "USD",
            "final_payout": "12.50",
        }
    )
    cost = {metric["id"]: metric for metric in calculate_measurement_result(manifest)["metrics"]}[
        "driver_campaign_cost"
    ]

    assert cost["totals_by_currency"] == [
        {"currency": "NGN", "value": "800.00"},
        {"currency": "USD", "value": "12.50"},
    ]
    assert cost["completeness"]["covered_trip_count"] == 2
    assert cost["completeness"]["complete"] is True
    assert cost["completeness"]["suppressed"] is False


def test_density_provenance_without_a_road_category_method_suppresses_contacts() -> None:

    manifest = _disclosure_manifest()
    del manifest["sources"]["impression_estimates"][0]["provenance"]["road_category_method"]
    contacts = {
        metric["id"]: metric for metric in calculate_measurement_result(manifest)["metrics"]
    }["modelled_potential_contacts"]

    assert contacts["density_provenance"]["profiles"] == []
    assert contacts["completeness"]["suppressed"] is True
    assert contacts["value"] is None


def test_reproducibility_fails_closed_for_a_manifest_that_predates_this_contract() -> None:
    # A stored run whose manifest no longer satisfies the frozen contract must report
    # "not reproducible" so callers render their fail-closed state, never raise a 500.
    from app.services.historical_measurement import canonical_sha256

    legacy_manifest = {"schema_version": "measurement-input-manifest-v0"}
    run = MeasurementRun(
        input_manifest=legacy_manifest,
        input_manifest_sha256=canonical_sha256(legacy_manifest),
        proof_manifest={},
        proof_manifest_sha256=canonical_sha256({}),
        report_snapshot={},
        report_snapshot_sha256=canonical_sha256({}),
        result_manifest={},
        result_manifest_sha256=canonical_sha256({}),
    )
    run.input_manifest["disclosure_authority"] = {
        "report_snapshot_sha256": run.report_snapshot_sha256
    }
    run.input_manifest_sha256 = canonical_sha256(run.input_manifest)

    assert measurement_run_reproducible(run) is False


def test_frozen_modelled_contacts_freeze_density_parameter_source_and_calibration() -> None:
    # MET-004

    contract = json.loads(
        (Path(__file__).resolve().parents[1] / "docs" / "measurement-methodology.json").read_text()
    )
    expected = next(
        row for row in contract["metric_hierarchy"] if row["id"] == "modelled_potential_contacts"
    )
    contacts = {
        metric["id"]: metric
        for metric in calculate_measurement_result(_disclosure_manifest())["metrics"]
    }["modelled_potential_contacts"]
    provenance = contacts["density_provenance"]

    assert provenance["source"] == expected["source"]
    assert provenance["calibration"] == expected["calibration"]
    assert provenance["profiles"] == [
        {
            "profile_id": "00000000-0000-4000-8000-0000000000a1",
            "lineage_id": "00000000-0000-4000-8000-0000000000b1",
            "revision": "2",
            "effective_from": "2026-07-01T00:00:00+00:00",
            "value_fingerprint": "9" * 64,
            "traffic_density_per_km": "180",
            "dwell_impressions_per_minute": "12",
            "road_category_method": "profile_default_weight_no_road_classification_v1",
        }
    ]
    # The existing model uncertainty wording is unchanged for downstream consumers.
    assert contacts["uncertainty"] == (
        "Model confidence is a diagnostic, not a statistical confidence interval."
    )
