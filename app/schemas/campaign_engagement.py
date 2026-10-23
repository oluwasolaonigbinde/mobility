import ipaddress
import re
from datetime import date
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def validated_website(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Enter a public https website link")
    if "\\" in value:
        raise ValueError("Enter a public https website link")
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").encode("idna").decode("ascii").lower()
        port = parsed.port
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Enter a public https website link") from exc
    if (
        parsed.scheme.lower() != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", hostname)
        or hostname.endswith((".localhost", ".local", ".internal", ".test", ".invalid", ".example"))
    ):
        raise ValueError("Enter a public https website link without a sign-in or custom port")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("Enter a public https website name")
    return urlunsplit(("https", hostname, parsed.path or "/", parsed.query, parsed.fragment))


class ArtworkLinkWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination: str = Field(max_length=2048)

    @field_validator("destination")
    @classmethod
    def website(cls, value: str) -> str:
        return validated_website(value)


class ScanDayRead(BaseModel):
    day: date
    scans: int = Field(ge=0)


class ArtworkLinkRead(BaseModel):
    creative_id: UUID
    destination: str | None
    short_path: str | None
    scans: int = Field(ge=0)
    days: list[ScanDayRead]


class CampaignScansRead(BaseModel):
    campaign_id: UUID
    scans: int = Field(ge=0)
    days: list[ScanDayRead]


class AnonymousPosition(BaseModel):
    longitude: float
    latitude: float


class LivePositionsRead(BaseModel):
    campaign_id: UUID
    delay_minutes: int = 15
    positions: list[AnonymousPosition]
