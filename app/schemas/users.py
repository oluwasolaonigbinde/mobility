from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.user import UserRole, UserStatus


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1)
    full_name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    role: Literal[UserRole.ADMIN, UserRole.DRIVER]
    status: UserStatus
    current_password: str | None = Field(
        default=None,
        min_length=1,
        json_schema_extra={"writeOnly": True},
    )

    @model_validator(mode="after")
    def drivers_start_active(self) -> "UserCreate":
        # REQ-315: a non-active account cannot sign in, so staff only create active drivers.
        if self.role == UserRole.DRIVER and self.status != UserStatus.ACTIVE:
            raise ValueError("Staff can only create a driver as active")
        return self


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    role: UserRole | None = None
    status: UserStatus | None = None
    current_password: str | None = Field(
        default=None,
        min_length=1,
        json_schema_extra={"writeOnly": True},
    )


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    phone: str | None
    role: UserRole
    status: UserStatus
    must_change_password: bool


class UserListResponse(BaseModel):
    items: list[UserRead]
    total: int
    limit: int
    offset: int
