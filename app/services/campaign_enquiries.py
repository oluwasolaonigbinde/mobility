from html import escape
from uuid import uuid4

from app.adapters.messaging.email import EmailAdapter, EmailMessage, EmailSendError
from app.core.errors import AppError
from app.schemas.campaign_enquiries import CampaignEnquiryCreate

CAMPAIGN_ENQUIRY_RECIPIENT = "terraxmediacompany@gmail.com"


async def send_campaign_enquiry(enquiry: CampaignEnquiryCreate, adapter: EmailAdapter) -> None:
    lines = [
        "Campaign quote enquiry — Terrax Media",
        f"Company: {enquiry.company}",
        f"Contact name: {enquiry.contact_name}",
        f"Reply email: {enquiry.email}",
        f"Phone: {enquiry.phone or 'Not supplied'}",
        "Campaign brief:",
        enquiry.brief,
    ]
    body = "\n".join(lines)
    message = EmailMessage(
        recipient=CAMPAIGN_ENQUIRY_RECIPIENT,
        subject="Campaign quote enquiry — Terrax Media",
        text_body=body,
        html_body=f"<pre>{escape(body)}</pre>",
        idempotency_key=f"campaign-enquiry-{uuid4()}",
    )
    try:
        await adapter.send(message)
    except EmailSendError:
        raise AppError(
            "campaign_enquiry_unavailable",
            "We could not confirm your enquiry was sent. Please contact Terrax by email.",
            status_code=503,
        ) from None
