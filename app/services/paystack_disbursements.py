from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.crypto import EnvelopeCryptoProvider
from app.adapters.disbursement import DisbursementInstruction
from app.adapters.disbursement.paystack import TransferDestination
from app.core.config import Settings
from app.core.errors import AppError
from app.services.payees import read_frozen_payout_bank_account


def build_paystack_destination_resolver(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
):
    """Build the audited resolver used only by provider submission workers."""

    crypto = EnvelopeCryptoProvider(
        keys=settings.payout_crypto_keys,
        active_key_version=settings.payout_crypto_key_version,
    )

    async def resolve(instruction: DisbursementInstruction) -> TransferDestination:
        try:
            payee_version_id = UUID(instruction.instruction["payee_version_id"])
            bank_account_version_id = UUID(
                instruction.instruction["bank_account_version_id"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError(
                "PAYOUT_DESTINATION_INSTRUCTION_INVALID",
                "The frozen payout instruction has no valid destination authority",
                status_code=409,
            ) from exc
        async with sessionmaker() as session:
            details = await read_frozen_payout_bank_account(
                session,
                payee_version_id=payee_version_id,
                bank_account_version_id=bank_account_version_id,
                crypto=crypto,
            )
            await session.commit()
        return TransferDestination(
            account_name=details.account_name,
            account_number=details.account_number,
            bank_code=details.bank_code,
        )

    return resolve
