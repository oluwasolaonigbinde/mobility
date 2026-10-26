"""REQ-208 / D106: plain driver email wording and the 24-hour account set-up link."""

from app.core.config import Settings
from app.models.notification import NotificationType
from app.services.email_templates import render_email_template


def test_account_setup_link_lasts_24_hours_and_says_so() -> None:
    assert Settings(environment="test").driver_account_setup_ttl_seconds == 24 * 60 * 60
    email = render_email_template(
        NotificationType.DRIVER_ACCOUNT_SETUP_REQUESTED.value,
        "v1",
        {"setup_action": "https://cardvert.example/driver-account-setup#token"},
    )
    assert "This link works once, for 24 hours." in email.text_body
    assert "minutes" not in email.text_body
