"""REQ-318: stored report snapshots no longer carry the unread ``areas_label``."""

import asyncio

from test_corrected_reports import graph, issue

from app.services.campaign_report_rendering import render_campaign_csv, render_campaign_pdf


def test_report_snapshot_has_no_areas_label_and_renders_the_same(db_sessionmaker, settings):
    admin, campaign = graph(db_sessionmaker, "req318")

    async def exercise():
        return await issue(db_sessionmaker, admin, campaign, settings)

    report = asyncio.run(exercise())
    item = report.snapshot["campaigns"][0]
    assert "areas_label" not in item
    # The renderers never read it: putting it back changes no byte.
    legacy = {**report.snapshot, "campaigns": [{**item, "areas_label": "Full weeks only"}]}
    assert render_campaign_csv(legacy) == render_campaign_csv(report.snapshot)
    assert render_campaign_pdf(legacy) == render_campaign_pdf(report.snapshot)
