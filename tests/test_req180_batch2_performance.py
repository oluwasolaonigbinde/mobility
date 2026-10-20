from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.services.campaign_performance import performance_from_manifest
from app.services.measurement import DENSITY_PROFILE_PROVENANCE_FIELDS

START = datetime(2026, 6, 1, tzinfo=UTC)
END = START + timedelta(days=7)


def manifest_for_cars(count):
    area = str(uuid4())
    manifest = {
        "formula_version": "measurement-result-v2",
        "period": {"start_at": START.isoformat(), "end_at": END.isoformat()},
        "cohort": [],
        "sources": {"trip_analytics": [], "impression_estimates": []},
        "audience_exposure_authority": {
            "resolution_m": 500,
            "window_start_at": START.isoformat(),
            "window_end_at": END.isoformat(),
            "rows": [],
        },
    }
    for index in range(count):
        trip, vehicle = str(uuid4()), str(uuid4())
        # Both UTC dates are the same Nigeria driving day.
        terminal = START + timedelta(hours=23, minutes=30 + index)
        manifest["cohort"].append(
            {"trip_session_id": trip, "status": "ended", "terminal_at": terminal.isoformat()}
        )
        manifest["sources"]["trip_analytics"].append(
            {
                "trip_session_id": trip,
                "vehicle_id": vehicle,
                "status": "computed",
                "distance_m": "1000.25",
            }
        )
        manifest["sources"]["impression_estimates"].append(
            {
                "trip_session_id": trip,
                "status": "estimated",
                "estimated_impressions": "30.00",
                "provenance": {
                    "road_category_method": "approved-test-method",
                    "traffic_density_profile": {
                        "id": str(uuid4()),
                        **{key: "test-profile" for key in DENSITY_PROFILE_PROVENANCE_FIELDS},
                    },
                },
            }
        )
        manifest["audience_exposure_authority"]["rows"].append(
            {
                "zone_id": area,
                "trip_session_id": trip,
                "vehicle_id": vehicle,
                "grid_x": 1,
                "grid_y": 1,
                "cell_ping_count": 10,
                "total_ping_count": 10,
                "recorded_days": [terminal.date().isoformat()],
            }
        )
    return manifest, {area: "Central area"}


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_coarse_totals_and_three_car_area_floor(count):
    manifest, labels = manifest_for_cars(count)
    result = performance_from_manifest(manifest, campaign_id=uuid4(), labels=labels)
    assert result.totals.trip_count == count
    assert result.totals.driving_days == (1 if count else 0)
    assert Decimal(result.totals.distance_m) == Decimal("1000.25") * count
    assert result.totals.estimated_views == (f"{30 * count}.00" if count else None)
    assert len(result.areas) == (1 if count == 3 else 0)
    if result.areas:
        assert result.areas[0].trip_count == 3
        assert result.areas[0].modelled_potential_contacts == "90.0000"


def test_area_contacts_allow_a_period_that_ends_mid_hour():
    # A completed or cancelled campaign's report can end at any minute.
    manifest, labels = manifest_for_cars(3)
    cutoff = (END - timedelta(minutes=17, seconds=5)).isoformat()
    manifest["period"]["end_at"] = cutoff
    manifest["audience_exposure_authority"]["window_end_at"] = cutoff
    manifest["audience_exposure_authority"]["rows"][0]["cell_ping_count"] = 4
    manifest["audience_exposure_authority"]["rows"].append(
        {**manifest["audience_exposure_authority"]["rows"][0], "grid_x": 2, "cell_ping_count": 6}
    )
    result = performance_from_manifest(manifest, campaign_id=uuid4(), labels=labels)
    assert result.areas[0].modelled_potential_contacts == "90.0000"


@pytest.mark.parametrize(
    ("case", "trip_count", "contacts"),
    [
        ("missing_estimate", 3, None),
        ("partial_cell", 3, "87.0000"),
        ("overlap", 3, "45.0000"),
        ("small_residual", 3, "90.0000"),
    ],
)
def test_three_car_area_is_the_only_area_rule(case, trip_count, contacts):
    # D105: no composition, coverage or residual rule withholds a three-car area.
    manifest, labels = manifest_for_cars(4 if case == "small_residual" else 3)
    rows = manifest["audience_exposure_authority"]["rows"]
    if case == "missing_estimate":
        estimate = manifest["sources"]["impression_estimates"].pop()
        manifest["sources"]["impression_estimates"].append({**estimate, "status": "failed"})
    elif case == "partial_cell":
        rows[0]["cell_ping_count"] = 9
    elif case == "overlap":
        other = str(uuid4())
        labels[other] = "Other area"
        for row in list(rows):
            row["cell_ping_count"] = 5
            rows.append({**row, "zone_id": other})
    else:
        rows.pop()
    result = performance_from_manifest(manifest, campaign_id=uuid4(), labels=labels)
    assert result.totals.trip_count == len(manifest["cohort"])
    assert result.areas
    assert {(row.trip_count, row.modelled_potential_contacts) for row in result.areas} == {
        (trip_count, contacts)
    }


def test_a_two_car_area_is_withheld_while_a_three_car_area_is_shown():
    manifest, labels = manifest_for_cars(5)
    rows = manifest["audience_exposure_authority"]["rows"]
    small = str(uuid4())
    labels[small] = "Small area"
    for row in rows[3:]:
        row["zone_id"] = small
    result = performance_from_manifest(manifest, campaign_id=uuid4(), labels=labels)
    assert [(row.name, row.trip_count) for row in result.areas] == [("Central area", 3)]


def test_three_trips_from_two_cars_do_not_release_an_area():
    manifest, labels = manifest_for_cars(3)
    first = manifest["sources"]["trip_analytics"][0]["vehicle_id"]
    manifest["sources"]["trip_analytics"][2]["vehicle_id"] = first
    manifest["audience_exposure_authority"]["rows"][2]["vehicle_id"] = first
    result = performance_from_manifest(manifest, campaign_id=uuid4(), labels=labels)
    assert result.totals.trip_count == 3
    assert result.areas == []


def test_inconsistent_area_authority_still_fails_closed():
    manifest, labels = manifest_for_cars(3)
    rows = manifest["audience_exposure_authority"]["rows"]
    rows.append({**rows[0], "grid_x": 2, "total_ping_count": 11})
    with pytest.raises(AppError) as error:
        performance_from_manifest(manifest, campaign_id=uuid4(), labels=labels)
    assert error.value.code == "REPORT_AREA_AUTHORITY_INVALID"
