"""REQ-208 / D106: plain driver email wording and the 24-hour account set-up link."""

import pytest

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


@pytest.mark.parametrize(
    ("notification_type", "subject", "body"),
    [
        (
            NotificationType.ACTIVITY_FLOOR_RECOVERED,
            "Weekly driving back on track",
            "You're back above this job's weekly minimum.",
        ),
        (
            NotificationType.ASSIGNMENT_ACTIVITY_RECOVERED,
            "Trips started again",
            "Trips are being recorded on your job again.",
        ),
    ],
)
def test_driver_recovery_emails_use_the_in_app_words(notification_type, subject, body) -> None:
    email = render_email_template(notification_type.value, "v1", {})
    assert (email.subject, email.text_body) == (subject, body)
    assert not {"floor", "verified", "operations", "assignment"} & set(
        email.text_body.lower().replace(".", "").split()
    )
