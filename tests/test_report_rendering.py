import csv
import hashlib
import io

import pytest

from app.services.report_rendering import (
    ReportRenderLimitError,
    _csv_cell,
    _pdf_report_lines,
    build_frozen_report_projection,
    render_report_csv,
    render_report_pdf,
)

MOVEMENT_CAVEAT = (
    "Completeness and quality scores describe collection quality; movement does not prove "
    "that a person saw an advert."
)


def completeness(*, covered: int, insufficient: int = 0, excluded: int = 0) -> dict:
    return {
        "cohort_trip_count": 3,
        "denominator_trip_count": 2,
        "in_progress_trip_count": 1,
        "covered_trip_count": covered,
        "insufficient_data_trip_count": insufficient,
        "excluded_trip_count": excluded,
        "complete": covered >= 2,
        "suppressed": covered == 0,
        "statement": (
            f"{covered} of 2 completed trips covered; {insufficient} insufficient-data and "
            f"{excluded} excluded trips are not zero-filled; 1 trips were still in progress."
        ),
    }


def density_profile(index: int) -> dict:
    return {
        "profile_id": f"00000000-0000-4000-8000-0000000000{index:02d}",
        "lineage_id": "00000000-0000-4000-8000-0000000000b1",
        "revision": str(index + 1),
        "effective_from": "2026-07-01T00:00:00+00:00",
        "value_fingerprint": str(index) * 64,
        "traffic_density_per_km": "180",
        "dwell_impressions_per_minute": "12",
        "road_category_method": "profile_default_weight_no_road_classification_v1",
    }


def export_snapshot(*, include_roi: bool = False, profile_count: int = 1) -> dict:
    snapshot = {
        "schema_version": "campaign-performance-export-v1",
        "title": "Campaign Performance Analysis",
        "synthetic": True,
        "creation_authority": "administrator",
        "issuance": {
            "id": "00000000-0000-4000-8000-000000000090",
            "version": 1,
            "schema_version": "campaign-performance-export-v1",
            "renderer_version": "campaign-report-renderer-v1",
            "created_at": "2026-08-28T00:00:00+00:00",
            "creation_authority": "administrator",
        },
        "measurement": {
            "run_id": "11111111-1111-1111-1111-111111111111",
            "input_sha256": "0" * 64,
            "result_sha256": "a" * 64,
            "proof_sha256": "b" * 64,
            "report_sha256": "c" * 64,
            "method_revision": "measurement-contract-v1",
            "formula_version": "measurement-result-v1",
            "period_start_at": "2026-08-01T00:00:00+00:00",
            "period_end_at": "2026-08-02T00:00:00+00:00",
        },
        "metrics": [
            {
                "id": "verified_vehicle_movement",
                "label": "=Verified vehicle movement",
                "class": "measured_operational_fact",
                "values": [
                    {"label": "Trip count", "value": "2", "unit": "trips"},
                    {"label": "Distance", "value": "1200.50", "unit": "metres"},
                ],
                "completeness": completeness(covered=2),
                "uncertainty": MOVEMENT_CAVEAT,
            },
            {
                "id": "modelled_potential_contacts",
                "label": "Modelled potential contacts",
                "class": "modelled_measure",
                "values": [{"label": "Value", "value": "100", "unit": "contacts"}],
                "completeness": completeness(covered=1, insufficient=1),
                "density_provenance": {
                    "source": "impressions_v1 output over verified vehicle movement",
                    "calibration": "Configured operational defaults; no field calibration.",
                    "profiles": [density_profile(index) for index in range(profile_count)],
                },
                "uncertainty": "@Synthetic only\r\nnot observed people",
            },
        ],
        "exposure": {
            "state": "suppressed",
            "score": None,
            "zones": [],
            "formula_version": "exposure_v1",
            "formula_fingerprint": "d" * 64,
            "input_fingerprint": "e" * 64,
            "segment_snapshot_hashes": [],
            "disclaimer": "No cell satisfied the disclosure floor.",
            "authority_fingerprint": "f" * 64,
        },
    }
    if include_roi:
        snapshot["financial_result"] = {
            "label": "Return on investment",
            "class": "conditional_financial_measure",
            "ratio": "1",
            "percent": "100",
            "currency": "NGN",
            "method_revision": "synthetic-roi-v1",
            "method": {
                "approval_reference": "SYNTHETIC_TEST_ONLY",
                "attribution_rule": "Synthetic conversion belongs to the fixture campaign.",
                "attribution_window": "Synthetic one-day fixture window.",
                "cost_basis": "Frozen driver campaign cost in NGN.",
                "exclusions": "No synthetic exclusions.",
                "corrections": "Reissue on changed fixture input.",
                "late_data": "Late fixture data requires reissue.",
                "limitations": "Advertiser-supplied inputs are not verified by Cardvert.",
            },
            "provenance": {
                "conversion_provenance": "SYNTHETIC_TEST_ONLY conversion fixture",
                "revenue_provenance": "SYNTHETIC_TEST_ONLY revenue fixture",
                "reporting_cutoff": "2026-08-02T00:00:00+00:00",
                "synthetic": True,
            },
        }
    return snapshot


def test_renderers_are_deterministic_formula_safe_and_share_the_snapshot() -> None:
    snapshot = export_snapshot(include_roi=True)

    first_csv = render_report_csv(snapshot)
    second_csv = render_report_csv(snapshot)
    first_pdf = render_report_pdf(snapshot)
    second_pdf = render_report_pdf(snapshot)

    assert first_csv == second_csv
    assert first_pdf == second_pdf
    assert hashlib.sha256(first_csv).hexdigest() == hashlib.sha256(second_csv).hexdigest()
    assert first_csv.startswith(b"section,metric_id,label,metric_class,value,unit,provenance\n")
    assert b"'=Verified vehicle movement" in first_csv
    assert b"'@Synthetic only not observed people" in first_csv
    assert b"00000000-0000-4000-8000-000000000090" in first_csv
    assert b"campaign-report-renderer-v1" in first_csv
    assert b"Return on investment" in first_csv
    assert b"100" in first_csv
    assert first_pdf.startswith(b"%PDF-1.4")
    assert b"/JavaScript" not in first_pdf
    assert b"/URI" not in first_pdf
    assert b"/FontFile2" in first_pdf
    assert b"/ToUnicode" in first_pdf
    assert "Return on investment" in "\n".join(_pdf_report_lines(snapshot))


def test_performance_only_artifacts_contain_no_roi_text() -> None:
    snapshot = export_snapshot()

    csv_content = render_report_csv(snapshot).lower()
    pdf_lines = "\n".join(_pdf_report_lines(snapshot)).lower()

    assert b"roi" not in csv_content
    assert b"return on investment" not in csv_content
    assert "roi" not in pdf_lines
    assert "return on investment" not in pdf_lines


def test_renderers_enforce_field_row_page_and_output_bounds() -> None:
    too_many_rows = export_snapshot()
    too_many_rows["metrics"][0]["values"] = [
        {"label": f"row-{index}", "value": "1", "unit": "count"} for index in range(501)
    ]
    with pytest.raises(ReportRenderLimitError, match="row limit"):
        render_report_csv(too_many_rows)
    with pytest.raises(ReportRenderLimitError, match="row limit"):
        render_report_pdf(too_many_rows)

    too_long = export_snapshot()
    too_long["metrics"][0]["label"] = "界" * 5000
    with pytest.raises(ReportRenderLimitError, match="field limit"):
        render_report_csv(too_long)
    with pytest.raises(ReportRenderLimitError, match="field limit"):
        render_report_pdf(too_long)


def test_csv_pdf_and_screen_contract_share_one_frozen_projection() -> None:
    # REP-003: all exports consume one typed row projection rather than parallel formatting.
    snapshot = export_snapshot(include_roi=True)

    projection = build_frozen_report_projection(snapshot)
    csv_rows = list(csv.reader(io.StringIO(render_report_csv(snapshot).decode("utf-8"))))
    pdf_lines = _pdf_report_lines(snapshot)

    assert [tuple(row) for row in csv_rows[1:]] == [
        tuple(_csv_cell(value) for value in row.as_csv_row()) for row in projection.rows
    ]
    for row in projection.rows:
        assert row.as_pdf_line() in pdf_lines

    period = next(row for row in projection.rows if row.metric_id == "period")
    timezone = next(row for row in projection.rows if row.metric_id == "timestamp_timezone")
    rounding = next(row for row in projection.rows if row.metric_id == "rounding")
    financial_currency = next(row for row in projection.rows if row.metric_id == "currency")
    assert f"input={snapshot['measurement']['input_sha256']}" in period.provenance
    assert timezone.value == "UTC"
    assert rounding.value == "Exact frozen decimal strings"
    assert snapshot["financial_result"]["currency"] in "\n".join(pdf_lines)
    assert financial_currency.value == snapshot["financial_result"]["currency"]


def test_unicode_labels_are_embedded_in_the_pdf_without_ascii_replacement() -> None:
    snapshot = export_snapshot()
    snapshot["metrics"][0]["label"] = "Lágos — ụgbọala"

    projection = build_frozen_report_projection(snapshot)
    pdf_content = render_report_pdf(snapshot)

    assert any(row.label == "Lágos — ụgbọala - Distance" for row in projection.rows)
    assert "Lágos — ụgbọala - Distance" in "\n".join(_pdf_report_lines(snapshot))
    assert b"/FontFile2" in pdf_content
    assert b"/ToUnicode" in pdf_content


def test_suppressed_totals_are_omitted_rather_than_zero_filled() -> None:
    snapshot = export_snapshot()
    snapshot["metrics"][1]["values"] = [
        {"label": "Value", "value": "omitted - insufficient frozen evidence", "unit": "contacts"}
    ]
    snapshot["metrics"][1]["completeness"] = completeness(covered=0, insufficient=2)

    csv_content = render_report_csv(snapshot).decode("utf-8")
    pdf_content = "\n".join(_pdf_report_lines(snapshot))

    assert "omitted - insufficient frozen evidence" in csv_content
    assert "omitted - insufficient frozen evidence" in pdf_content
    assert "suppressed=True" in pdf_content
    assert "suppressed=True" in csv_content


def test_multi_profile_density_provenance_stays_inside_renderer_bounds() -> None:
    snapshot = export_snapshot(include_roi=True, profile_count=24)

    csv_content = render_report_csv(snapshot)
    pdf_content = render_report_pdf(snapshot)

    assert csv_content.count(b"\n") <= 500
    assert len(pdf_content) <= 1024 * 1024
    assert b"density parameter" in csv_content
