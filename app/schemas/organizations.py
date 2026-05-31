from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.organization import MembershipRole, MembershipStatus, OrganizationStatus
from app.schemas.users import UserRead


class AdvertiserOrganizationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    billing_email: str | None = Field(default=None, max_length=255)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    status: OrganizationStatus = OrganizationStatus.ACTIVE
    owner_user_id: UUID | None = None

    @field_validator("country_code", "currency")
    @classmethod
    def uppercase_optional_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.upper()


class AdvertiserOrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    billing_email: str | None
    country_code: str | None
    currency: str
    status: OrganizationStatus


class OrganizationMembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: MembershipRole
    status: MembershipStatus


class AdminOrganizationCreateResponse(BaseModel):
    organization: AdvertiserOrganizationRead
    owner_membership: OrganizationMembershipRead | None


class AdvertiserOrganizationContextResponse(BaseModel):
    organization: AdvertiserOrganizationRead
    membership: OrganizationMembershipRead


class MeAdvertiserOrganization(BaseModel):
    id: UUID
    name: str
    currency: str
    membership_role: MembershipRole
    membership_status: MembershipStatus


class MeResponse(BaseModel):
    user: UserRead
    advertiser_organization: MeAdvertiserOrganization | None
