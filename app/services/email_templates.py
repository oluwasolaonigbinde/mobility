from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from typing import Any

from app.models.notification import NotificationType


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    text_body: str
    html_body: str


def _static(subject: str, body: str) -> Callable[[dict[str, Any]], RenderedEmail]:
    def render(_payload: dict[str, Any]) -> RenderedEmail:
        return RenderedEmail(
            subject=subject,
            text_body=body,
            html_body=f"<p>{body}</p>",
        )

    return render


def _password_reset(payload: dict[str, Any]) -> RenderedEmail:
    action = payload.get("reset_action")
    if not isinstance(action, str) or not action:
        raise ValueError("password_reset_action_missing")
    body = f"Use this single-use password reset action before it expires: {action}"
    return RenderedEmail(
        subject="Reset your Cardvert password",
        text_body=body,
        html_body=f"<p>{escape(body)}</p>",
    )


_TEMPLATES: dict[NotificationType, Callable[[dict[str, Any]], RenderedEmail]] = {
    NotificationType.PASSWORD_RESET_REQUESTED: _password_reset,
    NotificationType.CAMPAIGN_APPROVED: _static(
        "Campaign approved", "Your campaign has been approved."
    ),
    NotificationType.FUNDING_CONFIRMED: _static(
        "Campaign funding confirmed", "Campaign funding has been confirmed."
    ),
    NotificationType.BUDGET_ALERT: _static(
        "Campaign budget alert", "A configured campaign budget alert threshold was reached."
    ),
    NotificationType.CAMPAIGN_BUDGET_PAUSED: _static(
        "Campaign paused for budget", "A campaign was paused by the configured budget policy."
    ),
    NotificationType.CAMPAIGN_BUDGET_RESUMED: _static(
        "Campaign resumed", "An administrator resumed a budget-paused campaign."
    ),
    NotificationType.CAMPAIGN_CANCELLED: _static(
        "Campaign cancelled", "A campaign cancellation has been recorded."
    ),
    NotificationType.FRAUD_HOLD_RAISED: _static(
        "Trip payment on hold", "A trip payment is on hold while it is reviewed."
    ),
    NotificationType.FRAUD_REVIEW_RESOLVED: _static(
        "Fraud review resolved", "Your fraud review has been resolved."
    ),
    NotificationType.FRAUD_DISPUTE_REPLIED: _static(
        "Fraud dispute update", "Your fraud dispute has received a reply."
    ),
    NotificationType.ACTIVITY_FLOOR_BREACHED: _static(
        "Verified activity below floor",
        "Verified activity was below the configured weekly floor.",
    ),
    NotificationType.ACTIVITY_FLOOR_RECOVERED: _static(
        "Verified activity recovered",
        "Verified activity recovered to the configured weekly floor.",
    ),
    NotificationType.ASSIGNMENT_INACTIVE: _static(
        "Assignment inactive", "No verified activity was recorded for this assignment."
    ),
    NotificationType.ASSIGNMENT_ACTIVITY_RECOVERED: _static(
        "Assignment activity resumed", "Verified activity resumed for this assignment."
    ),
}


def render_email_template(
    type_key: str, template_version: str, payload: dict[str, Any]
) -> RenderedEmail:
    if template_version != "v1":
        raise ValueError("unsupported_email_template_version")
    try:
        renderer = _TEMPLATES[NotificationType(type_key)]
    except (KeyError, ValueError) as exc:
        raise ValueError("unsupported_email_notification_type") from exc
    return renderer(payload)
