from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from app.adapters.payments import (
    DisabledPaymentGatewayAdapter,
    PaymentWebhookAuthenticationError,
    PaymentWebhookPayloadError,
)
from app.adapters.payments.paystack import (
    PaystackPaymentGatewayAdapter,
    build_payment_gateway_adapter,
)
from app.api.v1.dependencies import (
    PaymentEventEnqueuerDependency,
    SessionDependency,
    SettingsDependency,
)
from app.core.errors import AppError
from app.schemas.billing import PaystackWebhookReceipt
from app.services.billing import ingest_payment_gateway_webhook

router = APIRouter(prefix="/webhooks", tags=["Provider webhooks"])


def get_paystack_payment_adapter(
    settings: SettingsDependency,
) -> PaystackPaymentGatewayAdapter | DisabledPaymentGatewayAdapter:
    return build_payment_gateway_adapter(settings)


PaystackAdapterDependency = Annotated[
    PaystackPaymentGatewayAdapter | DisabledPaymentGatewayAdapter,
    Depends(get_paystack_payment_adapter),
]


@router.post("/paystack", response_model=PaystackWebhookReceipt)
async def paystack_webhook(
    request: Request,
    session: SessionDependency,
    adapter: PaystackAdapterDependency,
    enqueuer: PaymentEventEnqueuerDependency,
    signature: str | None = Header(default=None, alias="X-Paystack-Signature"),
) -> PaystackWebhookReceipt:
    """Record Cardvert charge events; acknowledge every other signed event unprocessed.

    Transfer outcomes are reconciled by the admin poll until a queued transfer-event
    path exists (§15.4 keeps business logic out of the webhook request path).
    """
    if signature is None or not signature.strip():
        raise AppError(
            "PAYMENT_WEBHOOK_UNAUTHORIZED",
            "Payment webhook authentication failed",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if not isinstance(adapter, PaystackPaymentGatewayAdapter):
        raise AppError(
            "PAYMENT_PROVIDER_NOT_CONFIGURED",
            "Payment webhook verification is not configured",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    payload = await request.body()
    try:
        event_name, is_payment = adapter.classify_webhook(payload, signature)
    except PaymentWebhookAuthenticationError as exc:
        raise AppError(
            "INVALID_PAYMENT_WEBHOOK_SIGNATURE",
            "Payment webhook authentication or payload verification failed",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except PaymentWebhookPayloadError as exc:
        raise AppError(
            "INVALID_PAYMENT_WEBHOOK_PAYLOAD",
            "Authenticated payment webhook payload is invalid",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    if not is_payment:
        return PaystackWebhookReceipt(event=event_name, accepted=False, duplicate=False)
    event, created = await ingest_payment_gateway_webhook(
        session, adapter=adapter, payload=payload, signature=signature
    )
    await session.commit()
    await enqueuer.enqueue_payment_event(event.id)
    return PaystackWebhookReceipt(event=event_name, accepted=True, duplicate=not created)
