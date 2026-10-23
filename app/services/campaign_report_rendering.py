"""D118 allowlisted report data and PDF charts; never render private source rows."""

import base64
import csv
import io
import math
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape, quoteattr

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

RENDERER_VERSION = "campaign-report-d118-v1"
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MEASURED = (
    ("cars_deployed", "Cars deployed", "cars"),
    ("cars_driven", "Cars that drove", "cars"),
    ("distance_m", "Verified driving distance", "metres"),
    ("driving_days", "Driving days", "days"),
    ("trip_count", "Verified trips", "trips"),
    ("driving_seconds", "Driving time", "seconds"),
)
UNCERTAINTY = (
    "Views are estimates of potential contacts, not measured people or guaranteed views. "
    "The fixed model has no independent traffic survey or field calibration."
)


def _cell(value):
    result = "" if value is None else str(value)
    dangerous = result.lstrip(" \t\r\n").startswith(("=", "+", "-", "@"))
    return "'" + result if dangerous or result.startswith(("\t", "\r")) else result


def render_campaign_csv(snapshot: dict) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "campaign_id",
            "campaign",
            "status",
            "period_start",
            "period_end",
            "timezone",
            "section",
            "metric",
            "value",
            "unit",
            "date",
            "area",
            "artwork",
        ]
    )
    for campaign in snapshot["campaigns"]:
        prefix = [
            campaign["id"],
            campaign["name"],
            campaign["status"],
            snapshot["start_date"],
            snapshot["end_date"],
            "WAT (Africa/Lagos)",
        ]

        def row(
            section, metric, value, unit="", day="", area="", artwork="", _prefix=tuple(prefix)
        ):
            writer.writerow(
                [_cell(v) for v in [*_prefix, section, metric, value, unit, day, area, artwork]]
            )

        row("Campaign", "Campaign start", campaign["start_at"])
        row("Campaign", "Campaign end", campaign["end_at"])
        for key, label, unit in MEASURED:
            row("Measured results", label, campaign["measured"][key], unit)
        row("Estimates", "Estimated views", campaign["estimates"]["views"], "estimated views")
        row("Estimates", "Estimate explanation", UNCERTAINTY)
        for item in campaign["daily"]:
            for key, label, unit in (
                ("distance_m", "Verified distance", "metres"),
                ("vehicle_count", "Cars that drove", "cars"),
                ("trip_count", "Verified trips", "trips"),
                ("driving_seconds", "Driving time", "seconds"),
                ("estimated_impressions", "Estimated views", "estimated views"),
            ):
                row("Daily chart data", label, item[key], unit, item["date"])
        for area in campaign["areas"]:
            row("Campaign areas", "Verified trips", area["trip_count"], "trips", area=area["name"])
            row(
                "Campaign areas",
                "Cars that drove",
                area["vehicle_count"],
                "cars",
                area=area["name"],
            )
            row(
                "Estimates",
                "Estimated views in area",
                area.get("estimated_views"),
                "estimated contacts",
                area=area["name"],
            )
        for creative in campaign["creatives"]:
            row("Creative previews", "Artwork", creative["content_type"], artwork=creative["label"])
            row(
                "Creative previews",
                "Preview link"
                if creative["preview_path"].startswith(("https://", "http://"))
                else "Preview app path",
                creative["preview_path"],
                artwork=creative["label"],
            )
    content = stream.getvalue().encode("utf-8-sig")
    if len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError("REPORT_TOO_LARGE")
    return content


def _number(value, unit=""):
    if value is None:
        return "Not enough verified data"
    number = Decimal(str(value))
    if unit == "metres":
        return f"{number / 1000:,.2f} km"
    if unit == "seconds":
        return f"{int(number) // 3600} h {(int(number) % 3600) // 60} min"
    return f"{number:,.0f}"


def _chart(items, *, key, title, estimated=False):
    drawing = Drawing(460, 145)
    ink = colors.HexColor("#1f2937")
    color = colors.HexColor("#b45309" if estimated else "#1d4ed8")
    drawing.add(String(0, 130, title, fontName="ReportSans", fontSize=10, fillColor=ink))
    values = [None if row[key] is None else float(row[key]) for row in items]
    if key == "distance_m":
        values = [None if value is None else value / 1000 for value in values]
    maximum = max((value for value in values if value is not None), default=0) or 1
    width = 420 / max(1, len(items))
    drawing.add(Line(25, 25, 450, 25, strokeColor=colors.HexColor("#cbd5e1")))
    drawing.add(String(0, 110, f"{maximum:,.0f}", fontName="ReportSans", fontSize=7))
    step = max(1, math.ceil(len(items) / 7))
    for index, (row, value) in enumerate(zip(items, values, strict=True)):
        x = 27 + index * width
        if value is None:
            drawing.add(Line(x, 26, x + max(1, width * 0.7), 30, strokeColor=colors.grey))
        elif value > 0:
            bar = Rect(x, 25, width * 0.7, value / maximum * 80)
            bar.fillColor = color
            bar.strokeColor = None
            drawing.add(bar)
        if index % step == 0:
            day = datetime.fromisoformat(row["date"]).strftime("%d %b")
            drawing.add(String(x, 12, day, fontName="ReportSans", fontSize=7))
    drawing.add(
        String(
            25,
            0,
            "WAT days; gaps mean results are withheld or still processing.",
            fontName="ReportSans",
            fontSize=7,
            fillColor=ink,
        )
    )
    return drawing


def render_campaign_pdf(snapshot: dict) -> bytes:
    if "ReportSans" not in pdfmetrics.getRegisteredFontNames():
        font = Path(__file__).parents[1] / "assets/report_fonts/DejaVuSans.ttf"
        pdfmetrics.registerFont(TTFont("ReportSans", str(font)))
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = "ReportSans"
    styles["Heading1"].keepWithNext = True
    styles["Heading2"].keepWithNext = True
    styles.add(
        ParagraphStyle(
            "ReportNote",
            fontName="ReportSans",
            fontSize=8,
            leading=12,
            textColor=colors.HexColor("#475569"),
        )
    )
    story = []

    def paragraph(text, style="Normal", href=None):
        content = escape(str(text))
        if href:
            content = f"<link href={quoteattr(href)}>{content}</link>"
        return Paragraph(content, styles[style])

    story.extend(
        [
            paragraph("Campaign report", "Title"),
            paragraph(
                f"{snapshot['start_date']} to {snapshot['end_date']} | Nigeria time (WAT)",
                "ReportNote",
            ),
            paragraph("Measured driving and estimated views are shown separately.", "ReportNote"),
            Spacer(1, 14),
        ]
    )
    for campaign in snapshot["campaigns"]:
        story.extend(
            [
                paragraph(campaign["name"], "Heading1"),
                paragraph(f"Status: {campaign['status'].replace('_', ' ').title()}", "ReportNote"),
                paragraph(
                    f"Campaign dates: {campaign['start_at']} to {campaign['end_at']}", "ReportNote"
                ),
                paragraph("Measured results", "Heading2"),
            ]
        )
        measured = [
            [paragraph(label), paragraph(_number(campaign["measured"][key], unit))]
            for key, label, unit in MEASURED
        ]
        table = Table(measured, colWidths=[235, 225], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.extend(
            [
                table,
                Spacer(1, 8),
                _chart(campaign["daily"], key="distance_m", title="Verified daily distance (km)"),
            ]
        )
        estimate = Table(
            [
                [
                    paragraph("Estimated views", "Heading2"),
                    paragraph(_number(campaign["estimates"]["views"]), "Heading2"),
                ]
            ],
            colWidths=[235, 225],
            hAlign="LEFT",
        )
        estimate.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff7ed")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.extend(
            [
                estimate,
                paragraph(UNCERTAINTY, "ReportNote"),
                Spacer(1, 8),
                _chart(
                    campaign["daily"],
                    key="estimated_impressions",
                    title="Estimated daily views",
                    estimated=True,
                ),
                paragraph("Campaign areas", "Heading2"),
            ]
        )
        for area in campaign["areas"]:
            detail = (
                f"{area['vehicle_count']} cars; {area['trip_count']} verified trips"
                if area["vehicle_count"] is not None
                else "Verified area results unavailable"
            )
            story.append(paragraph(f"{area['name']}: {detail}", "ReportNote"))
            story.append(
                paragraph(
                    f"Estimated views in this area: {_number(area.get('estimated_views'))}. "
                    "Estimates in overlapping areas must not be added as unique views.",
                    "ReportNote",
                )
            )
        if not campaign["areas"]:
            story.append(paragraph("No campaign areas in this reporting period.", "ReportNote"))
        story.extend(_creative_previews(campaign, paragraph))
        story.extend([paragraph(campaign["note"], "ReportNote"), Spacer(1, 20)])
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=(595.28, 841.89),
        leftMargin=48,
        rightMargin=48,
        topMargin=42,
        bottomMargin=42,
        title="Cardvert campaign report",
        author="Terrax",
        invariant=1,
    )

    def footer(canvas, doc):
        canvas.setFont("ReportSans", 8)
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.drawString(48, 23, "Cardvert | Nigeria time (WAT)")
        canvas.drawRightString(547, 23, f"Page {doc.page}")

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    content = buffer.getvalue()
    if len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError("REPORT_TOO_LARGE")
    return content


def _creative_previews(campaign, paragraph):
    story = []
    heading = paragraph("Creative previews", "Heading2")
    for index, creative in enumerate(campaign["creatives"]):
        preview = creative.get("preview_base64")
        if preview:
            image = Image(
                io.BytesIO(base64.b64decode(preview)),
                width=220,
                height=135,
                kind="direct",
                hAlign="LEFT",
            )
            content = [paragraph(creative["label"], "ReportNote"), image]
        else:
            content = [paragraph(f"{creative['label']} - PDF artwork", "ReportNote")]
        link = creative.get("preview_path", "")
        try:
            parsed = urlsplit(link)
            clickable = (
                parsed.scheme in {"https", "http"}
                and bool(parsed.netloc)
                and not parsed.username
                and not parsed.password
            )
        except ValueError:
            clickable = False
        content.append(
            paragraph(
                "Open artwork" if clickable else f"Artwork app path: {link}",
                "ReportNote",
                href=link if clickable else None,
            )
        )
        if index == 0:
            content.insert(0, heading)
        story.append(KeepTogether(content))
    if not campaign["creatives"]:
        story.append(KeepTogether([heading, paragraph("No artwork uploaded.", "ReportNote")]))
    return story
