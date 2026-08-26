import copy
from uuid import uuid4

import pytest

from app.adapters.crypto import (
    AssociatedData,
    CiphertextEnvelope,
    CryptoConfigurationError,
    CryptoOperationError,
    CustodyEnvelopeCryptoProvider,
    EnvelopeCryptoProvider,
    LocalKeyCustodyBackend,
)


def test_envelope_round_trip_is_ciphertext_only_and_repr_safe() -> None:
    plaintext = b'{"account_number":"0123456789","account_name":"Private Driver"}'
    provider = EnvelopeCryptoProvider(keys={7: b"k" * 32}, active_key_version=7)
    aad = AssociatedData(tenant_id=uuid4(), record_id=uuid4(), field_name="bank_account.details")

    encrypted = provider.encrypt(plaintext, aad)
    stored = encrypted.to_mapping()

    assert provider.decrypt(encrypted, aad) == plaintext
    assert encrypted.key_version == 7
    assert encrypted.nonce != encrypted.wrapped_key_nonce
    assert "0123456789" not in str(stored)
    assert "Private Driver" not in str(stored)
    assert "ciphertext=" not in repr(encrypted)
    assert "wrapped_key=" not in repr(encrypted)


@pytest.mark.parametrize("aad_field", ["other.field", "bank_account.details\x00other"])
def test_wrong_associated_data_fails_without_sensitive_error(aad_field: str) -> None:
    provider = EnvelopeCryptoProvider(keys={1: b"a" * 32}, active_key_version=1)
    tenant_id = uuid4()
    record_id = uuid4()
    encrypted = provider.encrypt(
        b"private-bank-value",
        AssociatedData(tenant_id=tenant_id, record_id=record_id, field_name="bank_account.details"),
    )

    with pytest.raises(CryptoOperationError) as caught:
        provider.decrypt(
            encrypted,
            AssociatedData(tenant_id=tenant_id, record_id=record_id, field_name=aad_field),
        )

    assert "private-bank-value" not in str(caught.value)


@pytest.mark.parametrize("field", ["ciphertext_b64", "wrapped_key_b64"])
def test_tampered_ciphertext_or_wrapped_key_fails_closed(field: str) -> None:
    provider = EnvelopeCryptoProvider(keys={1: b"b" * 32}, active_key_version=1)
    aad = AssociatedData(tenant_id=uuid4(), record_id=uuid4(), field_name="bank_account.details")
    stored = provider.encrypt(b"private-bank-value", aad).to_mapping()
    tampered = copy.deepcopy(stored)
    original = str(tampered[field])
    tampered[field] = ("A" if original[0] != "A" else "B") + original[1:]

    with pytest.raises(CryptoOperationError):
        provider.decrypt(CiphertextEnvelope.from_mapping(tampered), aad)


def test_rotation_rewraps_dek_without_reencrypting_data() -> None:
    aad = AssociatedData(tenant_id=uuid4(), record_id=uuid4(), field_name="bank_account.details")
    old_provider = EnvelopeCryptoProvider(keys={1: b"c" * 32}, active_key_version=1)
    encrypted = old_provider.encrypt(b"private-bank-value", aad)
    rotating_provider = EnvelopeCryptoProvider(
        keys={1: b"c" * 32, 2: b"d" * 32}, active_key_version=2
    )

    rotated = rotating_provider.rotate(encrypted, aad)

    assert rotated.key_version == 2
    assert rotated.nonce == encrypted.nonce
    assert rotated.ciphertext == encrypted.ciphertext
    assert rotated.wrapped_key_nonce != encrypted.wrapped_key_nonce
    assert rotated.wrapped_key != encrypted.wrapped_key
    assert rotating_provider.decrypt(encrypted, aad) == b"private-bank-value"
    assert rotating_provider.decrypt(rotated, aad) == b"private-bank-value"


def test_configuration_and_envelope_parsing_fail_closed() -> None:
    with pytest.raises(CryptoConfigurationError):
        EnvelopeCryptoProvider(keys={1: b"short"}, active_key_version=1)
    with pytest.raises(CryptoConfigurationError):
        EnvelopeCryptoProvider(keys={1: b"a" * 32}, active_key_version=2)

    provider = EnvelopeCryptoProvider(keys={1: b"a" * 32}, active_key_version=1)
    aad = AssociatedData(tenant_id=uuid4(), record_id=uuid4(), field_name="bank_account.details")
    stored = provider.encrypt(b"private-bank-value", aad).to_mapping()
    stored["data_algorithm"] = "unknown"
    with pytest.raises(CryptoOperationError):
        CiphertextEnvelope.from_mapping(stored)


def test_provider_neutral_custody_preserves_schema_and_rewraps_only_the_dek() -> None:
    aad = AssociatedData(tenant_id=uuid4(), record_id=uuid4(), field_name="driver_kyc.nin")
    old = CustodyEnvelopeCryptoProvider(
        custody=LocalKeyCustodyBackend(keys={1: b"a" * 32}, active_key_version=1)
    )
    encrypted = old.encrypt(b"12345678901", aad)
    rotating = CustodyEnvelopeCryptoProvider(
        custody=LocalKeyCustodyBackend(
            keys={1: b"a" * 32, 2: b"b" * 32}, active_key_version=2
        )
    )

    rotated = rotating.rotate(encrypted, aad)

    assert set(rotated.to_mapping()) == set(encrypted.to_mapping())
    assert rotated.key_version == 2
    assert rotated.nonce == encrypted.nonce
    assert rotated.ciphertext == encrypted.ciphertext
    assert rotating.decrypt(rotated, aad) == b"12345678901"


def test_unavailable_custody_fails_closed_without_plaintext_or_backend_detail() -> None:
    class UnavailableCustody:
        active_key_version = 1

        def wrap_key(self, plaintext_key: bytes, aad: bytes):
            del plaintext_key, aad
            raise OSError("vendor secret detail")

        def unwrap_key(self, key_version: int, nonce: bytes, wrapped_key: bytes, aad: bytes):
            del key_version, nonce, wrapped_key, aad
            raise OSError("vendor secret detail")

    provider = CustodyEnvelopeCryptoProvider(custody=UnavailableCustody())
    aad = AssociatedData(tenant_id=uuid4(), record_id=uuid4(), field_name="driver_kyc.nin")

    with pytest.raises(CryptoOperationError) as caught:
        provider.encrypt(b"12345678901", aad)

    assert "12345678901" not in str(caught.value)
    assert "vendor" not in str(caught.value)


def test_custody_cannot_claim_an_inactive_wrapping_version() -> None:
    class StaleCustody:
        active_key_version = 2

        def wrap_key(self, plaintext_key: bytes, aad: bytes):
            del plaintext_key, aad
            return 1, b"n" * 12, b"wrapped"

        def unwrap_key(self, key_version: int, nonce: bytes, wrapped_key: bytes, aad: bytes):
            del key_version, nonce, wrapped_key, aad
            return b"d" * 32

    provider = CustodyEnvelopeCryptoProvider(custody=StaleCustody())
    aad = AssociatedData(tenant_id=uuid4(), record_id=uuid4(), field_name="driver_kyc.nin")

    with pytest.raises(CryptoOperationError, match="invalid wrapped key data"):
        provider.encrypt(b"12345678901", aad)
