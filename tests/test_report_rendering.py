import hashlib

import pytest

from app.services.report_rendering import (
    ReportRenderLimitError,
    render_report_csv,
    render_report_pdf,
)


def export_snapshot(*, include_roi: bool = False) -> dict:
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
            },
            {
                "id": "modelled_potential_contacts",
                "label": "Modelled potential contacts",
                "class": "modelled_measure",
                "values": [{"label": "Value", "value": "100", "unit": "contacts"}],
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
    assert b"Return on investment" in first_pdf
    assert first_pdf.count(b") Tj") > 20


def test_performance_only_artifacts_contain_no_roi_text() -> None:
    snapshot = export_snapshot()

    csv_content = render_report_csv(snapshot).lower()
    pdf_content = render_report_pdf(snapshot).lower()

    assert b"roi" not in csv_content
    assert b"return on investment" not in csv_content
    assert b"roi" not in pdf_content
    assert b"return on investment" not in pdf_content


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
