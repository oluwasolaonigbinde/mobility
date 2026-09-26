"""Per-purpose upload limits and types (client answer #12, 24 Sep 2026)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.stored_file import FilePurpose
from app.schemas.stored_files import MB, FileUploadCreate


def upload(purpose: FilePurpose, content_type: str, size_bytes: int) -> FileUploadCreate:
    return FileUploadCreate(
        client_request_id=uuid4(),
        purpose=purpose,
        filename="file",
        content_type=content_type,
        size_bytes=size_bytes,
        sha256="a" * 64,
    )


@pytest.mark.parametrize(
    ("purpose", "content_type", "limit"),
    [
        (FilePurpose.CREATIVE, "video/mp4", 25 * MB),
        (FilePurpose.DRIVER_KYC, "application/pdf", 10 * MB),
        # Registration and insurance papers are vehicle evidence too.
        (FilePurpose.VEHICLE_EVIDENCE, "application/pdf", 20 * MB),
        (FilePurpose.INSTALLATION_EVIDENCE, "image/jpeg", 20 * MB),
    ],
)
def test_each_purpose_accepts_up_to_its_own_limit(purpose, content_type, limit) -> None:
    assert upload(purpose, content_type, limit).size_bytes == limit
    # Artwork's limit is also the field-wide maximum, which pydantic checks first.
    refused = f"larger than the {limit // MB} MB|less than or equal"
    with pytest.raises(ValidationError, match=refused):
        upload(purpose, content_type, limit + 1)


@pytest.mark.parametrize(
    ("purpose", "content_type"),
    [
        (FilePurpose.DRIVER_KYC, "video/mp4"),
        (FilePurpose.VEHICLE_EVIDENCE, "video/mp4"),
        (FilePurpose.INSTALLATION_EVIDENCE, "application/pdf"),
        (FilePurpose.CREATIVE, "text/html"),
    ],
)
def test_each_purpose_refuses_types_outside_its_policy(purpose, content_type) -> None:
    with pytest.raises(ValidationError, match="not allowed for this upload"):
        upload(purpose, content_type, MB)


def test_report_exports_cannot_be_uploaded() -> None:
    with pytest.raises(ValidationError, match="cannot be uploaded"):
        upload(FilePurpose.REPORT_EXPORT, "application/pdf", MB)


def test_content_type_is_normalised_before_the_policy_check() -> None:
    assert upload(FilePurpose.DRIVER_KYC, " IMAGE/PNG ", MB).content_type == "image/png"
