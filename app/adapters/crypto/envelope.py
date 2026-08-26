import base64
import binascii
import struct
from collections.abc import Mapping
from dataclasses import dataclass, field
from os import urandom
from typing import Protocol, runtime_checkable
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENVELOPE_FORMAT_VERSION = 1
DATA_ALGORITHM = "AES-256-GCM"
KEY_WRAP_ALGORITHM = "AES-256-GCM"
NONCE_BYTES = 12
KEY_BYTES = 32


class CryptoConfigurationError(RuntimeError):
    """A non-secret crypto configuration value is invalid."""


class CryptoOperationError(RuntimeError):
    """A crypto operation failed without exposing sensitive input or backend detail."""


@dataclass(frozen=True, slots=True)
class AssociatedData:
    tenant_id: UUID
    record_id: UUID
    field_name: str

    def canonical_bytes(self) -> bytes:
        field_bytes = self.field_name.encode("utf-8")
        if not field_bytes or len(field_bytes) > 255:
            raise CryptoOperationError("Associated data is invalid")
        parts = (
            b"cardvert-envelope-aad",
            bytes([ENVELOPE_FORMAT_VERSION]),
            self.tenant_id.bytes,
            self.record_id.bytes,
            field_bytes,
        )
        return b"".join(struct.pack(">I", len(part)) + part for part in parts)


@dataclass(frozen=True, slots=True)
class CiphertextEnvelope:
    format_version: int
    data_algorithm: str
    key_wrap_algorithm: str
    key_version: int
    nonce: bytes = field(repr=False)
    ciphertext: bytes = field(repr=False)
    wrapped_key_nonce: bytes = field(repr=False)
    wrapped_key: bytes = field(repr=False)

    def to_mapping(self) -> dict[str, str | int]:
        return {
            "format_version": self.format_version,
            "data_algorithm": self.data_algorithm,
            "key_wrap_algorithm": self.key_wrap_algorithm,
            "key_version": self.key_version,
            "nonce_b64": base64.b64encode(self.nonce).decode("ascii"),
            "ciphertext_b64": base64.b64encode(self.ciphertext).decode("ascii"),
            "wrapped_key_nonce_b64": base64.b64encode(self.wrapped_key_nonce).decode("ascii"),
            "wrapped_key_b64": base64.b64encode(self.wrapped_key).decode("ascii"),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "CiphertextEnvelope":
        expected = {
            "format_version",
            "data_algorithm",
            "key_wrap_algorithm",
            "key_version",
            "nonce_b64",
            "ciphertext_b64",
            "wrapped_key_nonce_b64",
            "wrapped_key_b64",
        }
        if set(value) != expected:
            raise CryptoOperationError("Encrypted value has an invalid format")
        try:
            format_version = int(value["format_version"])
            key_version = int(value["key_version"])
            data_algorithm = str(value["data_algorithm"])
            key_wrap_algorithm = str(value["key_wrap_algorithm"])
            nonce = _decode_b64(value["nonce_b64"])
            ciphertext = _decode_b64(value["ciphertext_b64"])
            wrapped_key_nonce = _decode_b64(value["wrapped_key_nonce_b64"])
            wrapped_key = _decode_b64(value["wrapped_key_b64"])
        except (KeyError, TypeError, ValueError, binascii.Error):
            raise CryptoOperationError("Encrypted value has an invalid format") from None
        if (
            format_version != ENVELOPE_FORMAT_VERSION
            or data_algorithm != DATA_ALGORITHM
            or key_wrap_algorithm != KEY_WRAP_ALGORITHM
            or key_version < 1
            or len(nonce) != NONCE_BYTES
            or len(wrapped_key_nonce) != NONCE_BYTES
            or not ciphertext
            or not wrapped_key
        ):
            raise CryptoOperationError("Encrypted value has an invalid format")
        return cls(
            format_version=format_version,
            data_algorithm=data_algorithm,
            key_wrap_algorithm=key_wrap_algorithm,
            key_version=key_version,
            nonce=nonce,
            ciphertext=ciphertext,
            wrapped_key_nonce=wrapped_key_nonce,
            wrapped_key=wrapped_key,
        )


def _decode_b64(value: object) -> bytes:
    if not isinstance(value, str):
        raise TypeError
    return base64.b64decode(value.encode("ascii"), validate=True)


@runtime_checkable
class CryptoProvider(Protocol):
    @property
    def active_key_version(self) -> int: ...

    def encrypt(self, plaintext: bytes, associated_data: AssociatedData) -> CiphertextEnvelope: ...

    def decrypt(
        self, encrypted_value: CiphertextEnvelope, associated_data: AssociatedData
    ) -> bytes: ...

    def rotate(
        self, encrypted_value: CiphertextEnvelope, associated_data: AssociatedData
    ) -> CiphertextEnvelope: ...


@runtime_checkable
class KeyCustodyBackend(Protocol):
    """Adapter-private KEK custody; application services still use only CryptoProvider."""

    @property
    def active_key_version(self) -> int: ...

    def wrap_key(self, plaintext_key: bytes, aad: bytes) -> tuple[int, bytes, bytes]: ...

    def unwrap_key(
        self, key_version: int, nonce: bytes, wrapped_key: bytes, aad: bytes
    ) -> bytes: ...


class LocalKeyCustodyBackend:
    """Local/test custody backed by an explicitly versioned in-process keyring."""

    def __init__(self, *, keys: Mapping[int, bytes], active_key_version: int) -> None:
        if active_key_version not in keys or active_key_version < 1:
            raise CryptoConfigurationError("The active encryption key version is unavailable")
        if not keys or any(version < 1 or len(key) != KEY_BYTES for version, key in keys.items()):
            raise CryptoConfigurationError("Encryption keys must be versioned 32-byte values")
        self._keys = {version: bytes(key) for version, key in keys.items()}
        self._active_key_version = active_key_version

    @property
    def active_key_version(self) -> int:
        return self._active_key_version

    def wrap_key(self, plaintext_key: bytes, aad: bytes) -> tuple[int, bytes, bytes]:
        nonce = urandom(NONCE_BYTES)
        wrapped = AESGCM(self._keys[self._active_key_version]).encrypt(
            nonce,
            plaintext_key,
            _wrap_aad(aad, self._active_key_version),
        )
        return self._active_key_version, nonce, wrapped

    def unwrap_key(self, key_version: int, nonce: bytes, wrapped_key: bytes, aad: bytes) -> bytes:
        key = self._keys.get(key_version)
        if key is None:
            raise CryptoOperationError("Encrypted value key version is unavailable")
        try:
            return AESGCM(key).decrypt(nonce, wrapped_key, _wrap_aad(aad, key_version))
        except InvalidTag:
            raise CryptoOperationError("Encrypted value authentication failed") from None


class CustodyEnvelopeCryptoProvider:
    """D17 envelope provider whose KEK operations stay behind a custody backend."""

    def __init__(self, *, custody: KeyCustodyBackend) -> None:
        if custody.active_key_version < 1:
            raise CryptoConfigurationError("The active encryption key version is unavailable")
        self._custody = custody

    @property
    def active_key_version(self) -> int:
        return self._custody.active_key_version

    def encrypt(self, plaintext: bytes, associated_data: AssociatedData) -> CiphertextEnvelope:
        if not isinstance(plaintext, bytes) or not plaintext:
            raise CryptoOperationError("Plaintext must be non-empty bytes")
        aad = associated_data.canonical_bytes()
        dek = urandom(KEY_BYTES)
        nonce = urandom(NONCE_BYTES)
        ciphertext = AESGCM(dek).encrypt(nonce, plaintext, _data_aad(aad))
        try:
            key_version, wrapped_key_nonce, wrapped_key = self._custody.wrap_key(dek, aad)
        except CryptoOperationError:
            raise
        except Exception:
            raise CryptoOperationError("Encryption key custody is unavailable") from None
        _validate_wrapped_key(
            key_version,
            wrapped_key_nonce,
            wrapped_key,
            expected_version=self.active_key_version,
        )
        return CiphertextEnvelope(
            format_version=ENVELOPE_FORMAT_VERSION,
            data_algorithm=DATA_ALGORITHM,
            key_wrap_algorithm=KEY_WRAP_ALGORITHM,
            key_version=key_version,
            nonce=nonce,
            ciphertext=ciphertext,
            wrapped_key_nonce=wrapped_key_nonce,
            wrapped_key=wrapped_key,
        )

    def decrypt(
        self, encrypted_value: CiphertextEnvelope, associated_data: AssociatedData
    ) -> bytes:
        envelope = CiphertextEnvelope.from_mapping(encrypted_value.to_mapping())
        aad = associated_data.canonical_bytes()
        try:
            dek = self._custody.unwrap_key(
                envelope.key_version,
                envelope.wrapped_key_nonce,
                envelope.wrapped_key,
                aad,
            )
            return AESGCM(dek).decrypt(envelope.nonce, envelope.ciphertext, _data_aad(aad))
        except CryptoOperationError:
            raise
        except InvalidTag:
            raise CryptoOperationError("Encrypted value authentication failed") from None
        except Exception:
            raise CryptoOperationError("Encryption key custody is unavailable") from None

    def rotate(
        self, encrypted_value: CiphertextEnvelope, associated_data: AssociatedData
    ) -> CiphertextEnvelope:
        envelope = CiphertextEnvelope.from_mapping(encrypted_value.to_mapping())
        if envelope.key_version == self.active_key_version:
            return envelope
        aad = associated_data.canonical_bytes()
        try:
            dek = self._custody.unwrap_key(
                envelope.key_version,
                envelope.wrapped_key_nonce,
                envelope.wrapped_key,
                aad,
            )
            key_version, wrapped_key_nonce, wrapped_key = self._custody.wrap_key(dek, aad)
        except CryptoOperationError:
            raise
        except Exception:
            raise CryptoOperationError("Encryption key custody is unavailable") from None
        _validate_wrapped_key(
            key_version,
            wrapped_key_nonce,
            wrapped_key,
            expected_version=self.active_key_version,
        )
        return CiphertextEnvelope(
            format_version=envelope.format_version,
            data_algorithm=envelope.data_algorithm,
            key_wrap_algorithm=envelope.key_wrap_algorithm,
            key_version=key_version,
            nonce=envelope.nonce,
            ciphertext=envelope.ciphertext,
            wrapped_key_nonce=wrapped_key_nonce,
            wrapped_key=wrapped_key,
        )


class EnvelopeCryptoProvider(CustodyEnvelopeCryptoProvider):
    """Backward-compatible local/test D17 provider using an in-process keyring."""

    def __init__(self, *, keys: Mapping[int, bytes], active_key_version: int) -> None:
        super().__init__(
            custody=LocalKeyCustodyBackend(
                keys=keys,
                active_key_version=active_key_version,
            )
        )


def _validate_wrapped_key(
    key_version: int,
    nonce: bytes,
    wrapped_key: bytes,
    *,
    expected_version: int,
) -> None:
    if (
        key_version != expected_version
        or len(nonce) != NONCE_BYTES
        or not wrapped_key
    ):
        raise CryptoOperationError("Encryption key custody returned invalid wrapped key data")


def _data_aad(aad: bytes) -> bytes:
    return b"cardvert-envelope-data\x00" + aad


def _wrap_aad(aad: bytes, key_version: int) -> bytes:
    return b"cardvert-envelope-key-wrap\x00" + struct.pack(">I", key_version) + aad
