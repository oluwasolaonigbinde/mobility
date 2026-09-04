"""Deterministic, bounded renderers for frozen campaign report exports."""

from __future__ import annotations

import csv
import io
import json
import struct
import textwrap
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

MAX_INPUT_BYTES = 512 * 1024
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_ROWS = 500
MAX_FIELD_CHARACTERS = 2048
PDF_LINES_PER_PAGE = 48
MAX_PDF_PAGES = 16
PDF_LINE_CHARACTERS = 92
REPORT_TIMEZONE = "UTC"
PDF_FONT_PATH = Path(__file__).parents[1] / "assets" / "report_fonts" / "DejaVuSans.ttf"


class ReportRenderLimitError(ValueError):
    """A frozen report exceeds a fixed renderer safety boundary."""


@dataclass(frozen=True)
class FrozenReportRow:
    section: str
    metric_id: str
    label: str
    metric_class: str
    value: str
    unit: str
    provenance: str

    def as_csv_row(self) -> tuple[str, str, str, str, str, str, str]:
        return (
            self.section,
            self.metric_id,
            self.label,
            self.metric_class,
            self.value,
            self.unit,
            self.provenance,
        )

    def as_pdf_line(self) -> str:
        return (
            f"[{self.section} | {self.metric_id} | {self.metric_class}] {self.label}: "
            f"{self.value}{f' {self.unit}' if self.unit else ''} — {self.provenance}"
        )


@dataclass(frozen=True)
class FrozenReportProjection:
    rows: tuple[FrozenReportRow, ...]


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


def _utc_instant(value: object) -> str:
    try:
        instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReportRenderLimitError("report timestamp is invalid") from exc
    if instant.tzinfo is None:
        raise ReportRenderLimitError("report timestamp must include a timezone")
    return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_frozen_report_projection(snapshot: dict) -> FrozenReportProjection:
    """Normalize every frozen report fact once before any output renderer sees it."""
    _snapshot_size_guard(snapshot)
    measurement = snapshot["measurement"]
    provenance = (
        f"run={measurement['run_id']};input={measurement['input_sha256']};"
        f"result={measurement['result_sha256']};"
        f"proof={measurement['proof_sha256']};report={measurement['report_sha256']};"
        f"method={measurement['method_revision']};formula={measurement['formula_version']}"
    )
    issuance = snapshot.get("issuance")
    if not isinstance(issuance, dict):
        raise ReportRenderLimitError("report issuance identity is missing")
    issuance_provenance = (
        f"issuance={issuance['id']};version={issuance['version']};"
        f"schema={issuance['schema_version']};renderer={issuance['renderer_version']};"
        f"created={issuance['created_at']};authority={issuance['creation_authority']}"
    )
    rows: list[FrozenReportRow] = [
        FrozenReportRow(
            "report",
            "issuance",
            "Issuance identity",
            "immutable_evidence",
            str(issuance["id"]),
            f"version {issuance['version']}",
            issuance_provenance,
        ),
        FrozenReportRow(
            "report",
            "title",
            snapshot["title"],
            "report_identity",
            "synthetic" if snapshot["synthetic"] else "issued",
            "",
            f"{provenance};{issuance_provenance}",
        ),
        FrozenReportRow(
            "measurement",
            "period",
            "Reporting period",
            "frozen_period",
            f"{_utc_instant(measurement['period_start_at'])} to "
            f"{_utc_instant(measurement['period_end_at'])}",
            "",
            provenance,
        ),
        FrozenReportRow(
            "report",
            "timestamp_timezone",
            "Timestamp timezone",
            "display_contract",
            REPORT_TIMEZONE,
            "IANA timezone",
            "timestamps are frozen ISO-8601 instants displayed in UTC",
        ),
        FrozenReportRow(
            "report",
            "rounding",
            "Rounding",
            "display_contract",
            "Exact frozen decimal strings",
            "no browser rounding",
            "CSV, PDF and screen retain the frozen decimal representation",
        ),
    ]
    for metric in snapshot["metrics"]:
        metric_provenance = f"{provenance};formula={measurement['formula_version']}"
        for value in metric["values"]:
            rows.append(
                FrozenReportRow(
                    "performance",
                    metric["id"],
                    f"{metric['label']} - {value['label']}",
                    metric["class"],
                    value["value"],
                    value["unit"],
                    metric_provenance,
                )
            )
        completeness = metric.get("completeness")
        if completeness:
            rows.append(
                FrozenReportRow(
                    "performance",
                    metric["id"],
                    f"{metric['label']} - completeness",
                    metric["class"],
                    completeness["statement"],
                    "trips",
                    f"{metric_provenance};complete={completeness['complete']};"
                    f"suppressed={completeness['suppressed']}",
                )
            )
        density = metric.get("density_provenance")
        if density:
            rows.append(
                FrozenReportRow(
                    "performance",
                    metric["id"],
                    f"{metric['label']} - density source",
                    metric["class"],
                    density["source"],
                    "",
                    metric_provenance,
                )
            )
            rows.append(
                FrozenReportRow(
                    "performance",
                    metric["id"],
                    f"{metric['label']} - density calibration",
                    metric["class"],
                    density["calibration"],
                    "",
                    metric_provenance,
                )
            )
            for profile in density["profiles"]:
                rows.append(
                    FrozenReportRow(
                        "performance",
                        metric["id"],
                        f"{metric['label']} - density parameter",
                        metric["class"],
                        f"{profile['traffic_density_per_km']} per km; "
                        f"{profile['dwell_impressions_per_minute']} per dwell minute",
                        "traffic profile",
                        f"profile={profile['profile_id']};lineage={profile['lineage_id']};"
                        f"revision={profile['revision']};"
                        f"effective_from={profile['effective_from']};"
                        f"value_hash={profile['value_fingerprint']};"
                        f"road_category={profile['road_category_method']}",
                    )
                )
        if metric.get("uncertainty"):
            rows.append(
                FrozenReportRow(
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
        FrozenReportRow(
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
            FrozenReportRow(
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
            FrozenReportRow(
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
        FrozenReportRow(
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
        financial_provenance = f"{provenance};method={financial_result['method_revision']}"
        rows.append(
            FrozenReportRow(
                "financial_result",
                "currency",
                f"{financial_result['label']} - currency",
                financial_result["class"],
                financial_result["currency"],
                "ISO 4217 currency",
                financial_provenance,
            )
        )
        rows.extend(
            FrozenReportRow(
                "financial_result",
                field,
                financial_result["label"],
                financial_result["class"],
                financial_result[field],
                unit,
                financial_provenance,
            )
            for field, unit in (("ratio", "ratio"), ("percent", "percent"))
        )
        for field, value in sorted((financial_result.get("method") or {}).items()):
            rows.append(
                FrozenReportRow(
                    "financial_method",
                    field,
                    f"{financial_result['label']} - {field.replace('_', ' ')}",
                    financial_result["class"],
                    value,
                    "",
                    financial_provenance,
                )
            )
        for field, value in sorted((financial_result.get("provenance") or {}).items()):
            rows.append(
                FrozenReportRow(
                    "financial_provenance",
                    field,
                    f"{financial_result['label']} - {field.replace('_', ' ')}",
                    financial_result["class"],
                    str(value),
                    "",
                    financial_provenance,
                )
            )
    if len(rows) > MAX_ROWS:
        raise ReportRenderLimitError("report row limit exceeded")
    for row in rows:
        for value in row.as_csv_row():
            _bounded_text(value)
    return FrozenReportProjection(rows=tuple(rows))


def render_report_csv(snapshot: dict) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        ("section", "metric_id", "label", "metric_class", "value", "unit", "provenance")
    )
    for row in build_frozen_report_projection(snapshot).rows:
        writer.writerow(tuple(_csv_cell(value) for value in row.as_csv_row()))
    content = stream.getvalue().encode("utf-8")
    if len(content) > MAX_OUTPUT_BYTES:
        raise ReportRenderLimitError("report output byte limit exceeded")
    return content


@lru_cache(maxsize=1)
def _font_metadata() -> tuple[bytes, dict[int, int], int, int]:
    font = PDF_FONT_PATH.read_bytes()
    tables = {
        font[offset : offset + 4]: struct.unpack(">II", font[offset + 8 : offset + 16])
        for offset in range(12, 12 + struct.unpack(">H", font[4:6])[0] * 16, 16)
    }
    try:
        hhea_offset, _ = tables[b"hhea"]
        cmap_offset, _ = tables[b"cmap"]
    except KeyError as exc:
        raise ReportRenderLimitError("report PDF font is incomplete") from exc
    ascent, descent = struct.unpack(">hh", font[hhea_offset + 4 : hhea_offset + 8])
    cmap = _unicode_cmap(font, cmap_offset)
    return font, cmap, ascent, descent


def _unicode_cmap(font: bytes, cmap_offset: int) -> dict[int, int]:
    records = struct.unpack(">H", font[cmap_offset + 2 : cmap_offset + 4])[0]
    candidates = []
    for index in range(records):
        start = cmap_offset + 4 + index * 8
        platform_id, encoding_id, offset = struct.unpack(">HHI", font[start : start + 8])
        subtable = cmap_offset + offset
        fmt = struct.unpack(">H", font[subtable : subtable + 2])[0]
        if (platform_id, encoding_id) in {(0, 3), (3, 1), (3, 10)} and fmt in {4, 12}:
            candidates.append((fmt, subtable))
    if not candidates:
        raise ReportRenderLimitError("report PDF font has no Unicode cmap")
    fmt, subtable = max(candidates, key=lambda candidate: candidate[0])
    if fmt == 12:
        groups = struct.unpack(">I", font[subtable + 12 : subtable + 16])[0]
        mapping: dict[int, int] = {}
        for index in range(groups):
            start = subtable + 16 + index * 12
            first, last, glyph = struct.unpack(">III", font[start : start + 12])
            mapping.update(
                {codepoint: glyph + codepoint - first for codepoint in range(first, last + 1)}
            )
        return mapping
    seg_count = struct.unpack(">H", font[subtable + 6 : subtable + 8])[0] // 2
    end_codes = subtable + 14
    start_codes = end_codes + seg_count * 2 + 2
    id_deltas = start_codes + seg_count * 2
    id_range_offsets = id_deltas + seg_count * 2
    mapping = {}
    for index in range(seg_count):
        end = struct.unpack(">H", font[end_codes + index * 2 : end_codes + index * 2 + 2])[0]
        start = struct.unpack(">H", font[start_codes + index * 2 : start_codes + index * 2 + 2])[0]
        delta = struct.unpack(">h", font[id_deltas + index * 2 : id_deltas + index * 2 + 2])[0]
        range_offset = struct.unpack(
            ">H", font[id_range_offsets + index * 2 : id_range_offsets + index * 2 + 2]
        )[0]
        for codepoint in range(start, end + 1):
            if range_offset:
                glyph_offset = id_range_offsets + index * 2 + range_offset + (codepoint - start) * 2
                glyph = struct.unpack(">H", font[glyph_offset : glyph_offset + 2])[0]
                glyph = (glyph + delta) % 65536 if glyph else 0
            else:
                glyph = (codepoint + delta) % 65536
            mapping[codepoint] = glyph
    return mapping


def _pdf_font_objects(text: str) -> tuple[dict[int, bytes], dict[str, int]]:
    font, cmap, ascent, descent = _font_metadata()
    characters = sorted(set(text))
    unsupported = [character for character in characters if not cmap.get(ord(character), 0)]
    if unsupported:
        raise ReportRenderLimitError("report PDF font does not support a frozen Unicode character")
    cid_by_character = {character: index + 1 for index, character in enumerate(characters)}
    cid_to_gid = bytearray((len(characters) + 1) * 2)
    for character, cid in cid_by_character.items():
        cid_to_gid[cid * 2 : cid * 2 + 2] = struct.pack(">H", cmap[ord(character)])
    cmap_entries = []
    for character, cid in cid_by_character.items():
        encoded = character.encode("utf-16-be").hex().upper()
        cmap_entries.append(f"<{cid:04X}> <{encoded}>")
    character_map = "\n".join(cmap_entries)
    to_unicode = (
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /CardvertFrozenReport-UCS def\n/CMapType 2 def\n"
        "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        f"{len(cmap_entries)} beginbfchar\n"
        f"{character_map}\nendbfchar\nendcmap\n"
        "CMapName currentdict /CMap defineresource pop\nend\nend"
    ).encode("ascii")
    objects = {
        3: f"<< /Length {len(font)} /Length1 {len(font)} >>\nstream\n".encode("ascii")
        + font
        + b"\nendstream",
        4: (
            "<< /Type /FontDescriptor /FontName /CardvertFrozenReport "
            "/Flags 32 /FontBBox [-1021 -463 1793 1232] "
            f"/Ascent {ascent} /Descent {descent} /CapHeight {ascent} /ItalicAngle 0 "
            "/StemV 80 /FontFile2 3 0 R >>"
        ).encode("ascii"),
        5: (
            "<< /Type /Font /Subtype /CIDFontType2 /BaseFont /CardvertFrozenReport "
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
            "/FontDescriptor 4 0 R /DW 600 /CIDToGIDMap 6 0 R >>"
        ).encode("ascii"),
        6: f"<< /Length {len(cid_to_gid)} >>\nstream\n".encode("ascii")
        + bytes(cid_to_gid)
        + b"\nendstream",
        7: f"<< /Length {len(to_unicode)} >>\nstream\n".encode("ascii")
        + to_unicode
        + b"\nendstream",
        8: (
            "<< /Type /Font /Subtype /Type0 /BaseFont /CardvertFrozenReport "
            "/Encoding /Identity-H /DescendantFonts [5 0 R] /ToUnicode 7 0 R >>"
        ).encode("ascii"),
    }
    return objects, {character: cid for character, cid in cid_by_character.items()}


def _pdf_stream(lines: Iterable[str], character_cids: dict[str, int]) -> bytes:
    commands = ["BT", "/F1 9 Tf", "42 785 Td", "12 TL"]
    for line in lines:
        encoded = "".join(f"{character_cids[character]:04X}" for character in _bounded_text(line))
        commands.extend((f"<{encoded}> Tj", "T*"))
    commands.append("ET")
    return "\n".join(commands).encode("ascii")


def _pdf_document(pages: list[list[str]]) -> bytes:
    document_text = "".join(line for page in pages for line in page)
    font_objects, character_cids = _pdf_font_objects(document_text)
    page_ids = [9 + index * 2 for index in range(len(pages))]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Count {len(pages)} /Kids "
            f"[{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] >>"
        ).encode("ascii"),
    }
    objects.update(font_objects)
    for index, lines in enumerate(pages):
        page_id = page_ids[index]
        content_id = page_id + 1
        stream = _pdf_stream(lines, character_cids)
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 8 0 R >> >> /Contents {content_id} 0 R >>"
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
    projection = build_frozen_report_projection(snapshot)
    lines = [
        "Synthetic test artifact" if snapshot["synthetic"] else "Issued report artifact",
        "",
        "Frozen report projection",
        "Every row below is shared with the CSV and screen display contract.",
        "",
    ]
    lines.extend(row.as_pdf_line() for row in projection.rows)
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
