from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import UserRole, UserStatus


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1)
    full_name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    role: UserRole
    status: UserStatus


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    role: UserRole | None = None
    status: UserStatus | None = None


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
