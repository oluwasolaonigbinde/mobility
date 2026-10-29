"""Issue a synthetic test invoice so tests can record money against it (REQ-255)."""

from sqlalchemy import select

from app.core.config import Settings
from app.models.billing import Invoice, InvoiceStatus, IssuerVerificationStatus
from app.services.billing.invoices import (
    create_invoice_draft,
    issue_invoice,
    record_invoice_issuer_profile,
)


def _test_settings() -> Settings:
    return Settings(
        environment="test",
        database_url=None,
        redis_url=None,
        jwt_secret_key="test-secret-key-at-least-32-bytes",
    )


async def issue_test_invoice(session, *, terms, admin, settings: Settings | None = None) -> Invoice:
    """Issue the invoice for accepted terms through the real services (idempotent).

    Reuses an existing draft or issued invoice for the terms, so funding helpers may call it
    whether or not the test already created one.
    """
    settings = settings or _test_settings()
    existing = await session.scalar(select(Invoice).where(Invoice.commercial_terms_id == terms.id))
    if existing is not None and existing.status == InvoiceStatus.ISSUED:
        return existing
    issuer = await record_invoice_issuer_profile(
        session,
        actor_user_id=admin.id,
        legal_name="Terrax Media",
        tax_identification_number="TEST-TIN-ONLY",
        registered_address="Test fixture address, Abuja",
        country_code="NG",
        invoice_wording="VAT-inclusive test fixture invoice",
        numbering_prefix="TST",
        verification_status=IssuerVerificationStatus.SYNTHETIC,
        external_input_reference="SYNTHETIC-TEST-INVOICE-HELPER",
        settings=settings,
    )
    draft = existing or await create_invoice_draft(
        session, commercial_terms_id=terms.id, actor_user_id=admin.id
    )
    return await issue_invoice(
        session,
        invoice_id=draft.id,
        issuer_profile_id=issuer.id,
        actor_user_id=admin.id,
        settings=settings,
    )
