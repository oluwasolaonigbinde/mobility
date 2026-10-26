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


def _linked(subject: str, body: str, action: str | None, label: str) -> RenderedEmail:
    text = body + (f"\n{label}: {action}" if action else "")
    html = f"<p>{escape(body)}</p>"
    if action:
        from urllib.parse import urlsplit

        if urlsplit(action).scheme not in {"https", "http"}:
            raise ValueError("email_action_url_invalid")
        html += f'<p><a href="{escape(action, quote=True)}">{escape(label)}</a></p>'
    return RenderedEmail(subject=subject, text_body=text, html_body=html)


def _static(subject: str, body: str) -> Callable[[dict[str, Any]], RenderedEmail]:
    def render(payload: dict[str, Any]) -> RenderedEmail:
        name = payload.get("campaign_name")
        content = f"{name}: {body}" if name else body
        return _linked(subject, content, payload.get("action_url"), "Open Cardvert")

    return render


def _password_reset(payload: dict[str, Any]) -> RenderedEmail:
    action = payload.get("reset_action")
    if not isinstance(action, str) or not action:
        raise ValueError("password_reset_action_missing")
    return _linked(
        "Reset your Cardvert password",
        "Choose a new password. This link works once, for 30 minutes.",
        action,
        "Choose password",
    )


def _advertiser_login_invite(payload: dict[str, Any]) -> RenderedEmail:
    action = payload.get("reset_action")
    if not isinstance(action, str) or not action:
        raise ValueError("advertiser_invite_action_missing")
    return _linked(
        "Your Cardvert login invite",
        "Terrax Media has invited you to Cardvert. Choose a password, then sign in. "
        "This link works once, for 24 hours.",
        action,
        "Set password",
    )


def _report_ready(payload: dict[str, Any]) -> RenderedEmail:
    kind = payload.get("report_kind")
    name = payload.get("campaign_name")
    if (
        not isinstance(kind, str)
        or kind not in {"weekly", "final"}
        or not isinstance(name, str)
        or not name
    ):
        raise ValueError("report_ready_context_missing")
    return _linked(
        "Your Cardvert report is ready",
        f"Your {kind} report for {name} is ready",
        payload.get("action_url"),
        "View report",
    )


def _driver_onboarding_access(payload: dict[str, Any]) -> RenderedEmail:
    action = payload.get("action_url")
    if not isinstance(action, str) or not action:
        raise ValueError("driver_onboarding_link_missing")
    return _linked(
        "Continue your Terrax Media driver application",
        "Thanks for applying to drive with Terrax Media. Use this link to continue your "
        "application. It is valid for 24 hours. If it has expired, request a new link on Apply.",
        action,
        "Continue your application",
    )


def _driver_account_setup(payload: dict[str, Any]) -> RenderedEmail:
    action = payload.get("setup_action")
    return _linked(
        "Set up your Terrax Media driver account",
        (
            "Choose a password to finish setting up your driver account. "
            "This link works once, for 24 hours."
        )
        if action
        else "Ask Terrax Media to resend your account setup link.",
        action,
        "Choose password",
    )


def _driver_review(payload: dict[str, Any]) -> RenderedEmail:
    return _linked(payload["title"], payload["body"], payload["action_url"], "Continue")


_TEMPLATES: dict[NotificationType, Callable[[dict[str, Any]], RenderedEmail]] = {
    NotificationType.DRIVER_ID_APPROVED: _driver_review,
    NotificationType.DRIVER_ID_REJECTED: _driver_review,
    NotificationType.DRIVER_CAR_APPROVED: _driver_review,
    NotificationType.DRIVER_CAR_REJECTED: _driver_review,
    NotificationType.ASSIGNMENT_OFFERED: _static(
        "A new job offer", "You have a new job offer. Open Jobs to accept or decline."
    ),
    NotificationType.PASSWORD_RESET_REQUESTED: _password_reset,
    NotificationType.ADVERTISER_LOGIN_INVITE: _advertiser_login_invite,
    NotificationType.DRIVER_ONBOARDING_ACCESS_REQUESTED: _driver_onboarding_access,
    NotificationType.DRIVER_ACCOUNT_SETUP_REQUESTED: _driver_account_setup,
    NotificationType.CAMPAIGN_APPROVED: _static(
        "Campaign approved", "Your campaign has been approved."
    ),
    NotificationType.CAMPAIGN_REJECTED: _static(
        "Campaign needs changes",
        "Your campaign was not approved. Sign in to read the reason, update it and resubmit.",
    ),
    NotificationType.CREATIVE_APPROVED: _static(
        "Campaign artwork approved", "Campaign artwork has been approved."
    ),
    NotificationType.CREATIVE_REJECTED: _static(
        "Campaign artwork needs changes",
        "Campaign artwork was not approved. Sign in to read the reason.",
    ),
    NotificationType.QUOTATION_READY: _static(
        "Quotation ready for review", "A quotation is ready for your review. Sign in to review it."
    ),
    NotificationType.REPORT_READY: _report_ready,
    NotificationType.FUNDING_CONFIRMED: _static(
        "Campaign funding confirmed", "Campaign funding has been confirmed."
    ),
    NotificationType.BUDGET_ALERT: _static(
        "Campaign budget warning", "A campaign has used most of its budget."
    ),
    NotificationType.BUDGET_URGENT_ALERT: _static(
        "Campaign budget nearly used",
        "A campaign has almost used its budget and will pause when it runs out.",
    ),
    NotificationType.CAMPAIGN_BUDGET_PAUSED: _static(
        "Campaign paused for budget", "Cardvert paused a campaign because its budget is used up."
    ),
    NotificationType.CAMPAIGN_BUDGET_RESUMED: _static(
        "Campaign resumed", "Terrax Media resumed a campaign that was paused for budget."
    ),
    NotificationType.CAMPAIGN_CANCELLED: _static(
        "Campaign cancelled", "A campaign cancellation has been recorded."
    ),
    NotificationType.FRAUD_HOLD_RAISED: _static(
        "Trip payment on hold", "A trip payment is on hold while it is reviewed."
    ),
    NotificationType.FRAUD_REVIEW_RESOLVED: _static(
        "Your trip check is finished",
        "Terrax Media has finished checking your trip. Open Earnings to see the result.",
    ),
    NotificationType.FRAUD_DISPUTE_REPLIED: _static(
        "Reply about your trip",
        "Terrax Media has replied about your trip. Open Earnings to read it.",
    ),
    NotificationType.COMPLAINT_REPLIED: _static(
        "Terrax Media replied to your complaint",
        "Terrax Media Customer Service replied to your complaint. Sign in to read the reply.",
    ),
    NotificationType.COMPLAINT_RESOLVED: _static(
        "Your complaint is resolved",
        "Terrax Media Customer Service marked your complaint as resolved. Sign in to read it "
        "or reply if you still need help.",
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
