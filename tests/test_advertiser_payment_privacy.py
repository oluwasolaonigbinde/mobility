"""Advertiser financial contracts exclude internal driver-pay information."""

from app.main import create_app


def test_advertiser_responses_do_not_expose_driver_pay():
    schema = create_app().openapi()
    forbidden = {
        "requested_liability_amount",
        "available_liability_amount",
        "reserved_liability_amount",
        "impact_preview",
        "max_driver_liability",
        "final_payout_total",
        "gross_payout_total",
        "ledger_net_total",
        "costs",
    }

    def check(node, seen):
        if isinstance(node, dict):
            assert not forbidden.intersection(node.get("properties", {}))
            reference = node.get("$ref")
            if reference and reference not in seen:
                check(
                    schema["components"]["schemas"][reference.rsplit("/", 1)[1]], seen | {reference}
                )
            for value in node.values():
                check(value, seen)
        elif isinstance(node, list):
            for value in node:
                check(value, seen)

    for path, operations in schema["paths"].items():
        if "/advertiser/" in path:
            for operation in operations.values():
                check(operation.get("responses", {}), set())
    assert "/api/v1/advertiser/campaigns/{campaign_id}/cost-summary" not in schema["paths"]
