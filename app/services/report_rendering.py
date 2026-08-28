"""Deterministic, bounded renderers for frozen campaign report exports."""

from __future__ import annotations

import csv
import io
import json
import textwrap
import unicodedata
from collections.abc import Iterable

MAX_INPUT_BYTES = 512 * 1024
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_ROWS = 500
MAX_FIELD_CHARACTERS = 2048
PDF_LINES_PER_PAGE = 48
MAX_PDF_PAGES = 16
PDF_LINE_CHARACTERS = 92


class ReportRenderLimitError(ValueError):
    """A frozen report exceeds a fixed renderer safety boundary."""


def _bounded_text(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value))
    text = " ".join(text.replace("\x00", "").split())
    if len(text) > MAX_FIELD_CHARACTERS:
        raise ReportRenderLimitError("report field limit exceeded")
    return text


def _csv_cell(value: object) -> str:
    text = _bounded_text(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{text}"
    return text


def _snapshot_size_guard(snapshot: dict) -> None:
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_INPUT_BYTES:
        raise ReportRenderLimitError("report input byte limit exceeded")


def _rows(snapshot: dict) -> list[tuple[str, str, str, str, str, str, str]]:
    _snapshot_size_guard(snapshot)
    measurement = snapshot["measurement"]
    provenance = (
        f"run={measurement['run_id']};result={measurement['result_sha256']};"
        f"proof={measurement['proof_sha256']};report={measurement['report_sha256']};"
        f"method={measurement['method_revision']}"
    )
    issuance = snapshot.get("issuance")
    if not isinstance(issuance, dict):
        raise ReportRenderLimitError("report issuance identity is missing")
    issuance_provenance = (
        f"issuance={issuance['id']};version={issuance['version']};"
        f"schema={issuance['schema_version']};renderer={issuance['renderer_version']};"
        f"created={issuance['created_at']};authority={issuance['creation_authority']}"
    )
    rows: list[tuple[str, str, str, str, str, str, str]] = [
        (
            "report",
            "issuance",
            "Issuance identity",
            "immutable_evidence",
            str(issuance["id"]),
            f"version {issuance['version']}",
            issuance_provenance,
        ),
        (
            "report",
            "title",
            snapshot["title"],
            "report_identity",
            "synthetic" if snapshot["synthetic"] else "issued",
            "",
            f"{provenance};{issuance_provenance}",
        ),
        (
            "measurement",
            "period",
            "Reporting period",
            "frozen_period",
            f"{measurement['period_start_at']} to {measurement['period_end_at']}",
            "",
            provenance,
        ),
    ]
    for metric in snapshot["metrics"]:
        metric_provenance = f"{provenance};formula={measurement['formula_version']}"
        for value in metric["values"]:
            rows.append(
                (
                    "performance",
                    metric["id"],
                    f"{metric['label']} - {value['label']}",
                    metric["class"],
                    value["value"],
                    value["unit"],
                    metric_provenance,
                )
            )
        if metric.get("uncertainty"):
            rows.append(
                (
                    "performance",
                    metric["id"],
                    f"{metric['label']} - uncertainty",
                    metric["class"],
                    metric["uncertainty"],
                    "",
                    metric_provenance,
                )
            )
    exposure = snapshot["exposure"]
    exposure_provenance = (
        f"formula={exposure['formula_version']};"
        f"formula_hash={exposure['formula_fingerprint']};"
        f"input_hash={exposure['input_fingerprint']};"
        f"authority_hash={exposure['authority_fingerprint']};"
        f"segment_snapshot_hashes={','.join(exposure['segment_snapshot_hashes'])}"
    )
    rows.append(
        (
            "exposure",
            "disclosure_state",
            "Disclosure state",
            "privacy_control",
            exposure["state"],
            "",
            exposure_provenance,
        )
    )
    if exposure.get("score") is not None:
        rows.append(
            (
                "exposure",
                "exposure_score",
                "Exposure score",
                "operational_composite_index",
                exposure["score"],
                "points",
                exposure_provenance,
            )
        )
    for zone in exposure["zones"]:
        rows.append(
            (
                "exposure",
                "high_exposure_zone",
                zone["label"],
                "modelled_measure",
                zone["modelled_potential_contacts"],
                "modelled potential contacts",
                f"{exposure_provenance};rank={zone['rank']}",
            )
        )
    rows.append(
        (
            "exposure",
            "disclaimer",
            "Disclosure and uncertainty",
            "privacy_control",
            exposure["disclaimer"],
            "",
            exposure_provenance,
        )
    )
    financial_result = snapshot.get("financial_result")
    if financial_result is not None:
        rows.extend(
            (
                "financial_result",
                field,
                financial_result["label"],
                financial_result["class"],
                financial_result[field],
                unit,
                f"{provenance};method={financial_result['method_revision']}",
            )
            for field, unit in (("ratio", "ratio"), ("percent", "percent"))
        )
    if len(rows) > MAX_ROWS:
        raise ReportRenderLimitError("report row limit exceeded")
    for row in rows:
        for value in row:
            _bounded_text(value)
    return rows


def render_report_csv(snapshot: dict) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        ("section", "metric_id", "label", "metric_class", "value", "unit", "provenance")
    )
    for row in _rows(snapshot):
        writer.writerow(tuple(_csv_cell(value) for value in row))
    content = stream.getvalue().encode("utf-8")
    if len(content) > MAX_OUTPUT_BYTES:
        raise ReportRenderLimitError("report output byte limit exceeded")
    return content


def _pdf_text(value: object) -> str:
    text = _bounded_text(value).encode("ascii", "replace").decode("ascii")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_stream(lines: Iterable[str]) -> bytes:
    commands = ["BT", "/F1 9 Tf", "42 785 Td", "12 TL"]
    for line in lines:
        commands.extend((f"({_pdf_text(line)}) Tj", "T*"))
    commands.append("ET")
    return "\n".join(commands).encode("ascii")


def _pdf_document(pages: list[list[str]]) -> bytes:
    page_ids = [4 + index * 2 for index in range(len(pages))]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Count {len(pages)} /Kids "
            f"[{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] >>"
        ).encode("ascii"),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for index, lines in enumerate(pages):
        page_id = page_ids[index]
        content_id = page_id + 1
        stream = _pdf_stream(lines)
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id in range(1, max(objects) + 1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(objects[object_id])
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


def _pdf_report_lines(snapshot: dict) -> list[str]:
    # Exercise the same bounded row projection as CSV before creating a more
    # readable document layout from the identical frozen snapshot.
    _rows(snapshot)
    issuance = snapshot["issuance"]
    measurement = snapshot["measurement"]
    lines = [
        "Synthetic test artifact" if snapshot["synthetic"] else "Issued report artifact",
        "",
        "Issuance",
        f"Identity: {issuance['id']} (version {issuance['version']})",
        f"Schema: {issuance['schema_version']}",
        f"Renderer: {issuance['renderer_version']}",
        f"Created: {issuance['created_at']}",
        f"Creation authority: {issuance['creation_authority']}",
        "",
        "Frozen measurement provenance",
        f"Run: {measurement['run_id']}",
        f"Input SHA-256: {measurement.get('input_sha256', '')}",
        f"Result SHA-256: {measurement['result_sha256']}",
        f"Proof SHA-256: {measurement['proof_sha256']}",
        f"Report SHA-256: {measurement['report_sha256']}",
        f"Method: {measurement['method_revision']}",
        f"Formula: {measurement['formula_version']}",
        f"Period: {measurement['period_start_at']} to {measurement['period_end_at']}",
        "",
        "Performance metrics",
    ]
    for metric in snapshot["metrics"]:
        for value in metric["values"]:
            lines.append(
                f"{metric['label']} - {value['label']}: {value['value']} {value['unit']} "
                f"[{metric['class']}]"
            )
        if metric.get("uncertainty"):
            lines.append(f"Uncertainty: {metric['uncertainty']}")

    exposure = snapshot["exposure"]
    lines.extend(
        [
            "",
            "Disclosure and exposure",
            f"Disclosure state: {exposure['state']}",
        ]
    )
    if exposure.get("score") is not None:
        lines.append(f"Exposure score: {exposure['score']} points")
    for zone in exposure["zones"]:
        lines.append(
            f"Rank {zone['rank']}: {zone['label']} - "
            f"{zone['modelled_potential_contacts']} modelled potential contacts"
        )
    lines.extend(
        [
            f"Formula: {exposure['formula_version']}",
            f"Formula SHA-256: {exposure['formula_fingerprint']}",
            f"Input SHA-256: {exposure['input_fingerprint']}",
            f"Authority SHA-256: {exposure['authority_fingerprint']}",
        ]
    )
    for segment_hash in exposure["segment_snapshot_hashes"]:
        lines.append(f"Disclosure segment SHA-256: {segment_hash}")
    lines.append(f"Disclosure note: {exposure['disclaimer']}")
    if exposure.get("uncertainty"):
        lines.append(f"Exposure uncertainty: {exposure['uncertainty']}")

    financial_result = snapshot.get("financial_result")
    if financial_result is not None:
        lines.extend(
            [
                "",
                "Conditional financial result",
                f"{financial_result['label']}: {financial_result['ratio']} ratio; "
                f"{financial_result['percent']} percent; {financial_result['currency']}",
                f"Class: {financial_result['class']}",
                f"Method: {financial_result['method_revision']}",
            ]
        )
    return lines


def render_report_pdf(snapshot: dict) -> bytes:
    lines: list[str] = []
    for source_line in _pdf_report_lines(snapshot):
        lines.extend(
            textwrap.wrap(
                _bounded_text(source_line),
                width=PDF_LINE_CHARACTERS,
                subsequent_indent="  ",
                break_long_words=True,
                break_on_hyphens=False,
            )
            or [""]
        )
    content_pages = [
        lines[index : index + PDF_LINES_PER_PAGE]
        for index in range(0, len(lines), PDF_LINES_PER_PAGE)
    ]
    if len(content_pages) > MAX_PDF_PAGES:
        raise ReportRenderLimitError("report page limit exceeded")
    pages = [
        [snapshot["title"], f"Page {index} of {len(content_pages)}", "", *page]
        for index, page in enumerate(content_pages, start=1)
    ]
    content = _pdf_document(pages)
    if len(content) > MAX_OUTPUT_BYTES:
        raise ReportRenderLimitError("report output byte limit exceeded")
    return content
