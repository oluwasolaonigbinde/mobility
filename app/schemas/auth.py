from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import UserRole, UserStatus


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "email": "advertiser@demo.mobility.local",
                    "password": "DemoAdvertiser12345!",
                },
                {
                    "email": "driver@demo.mobility.local",
                    "password": "DemoDriver12345!",
                },
            ]
        },
    )

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1)


class LoginUser(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: UserRole
    status: UserStatus
    must_change_password: bool


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)


class PasswordResetComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=1)


class PasswordResetResponse(BaseModel):
    message: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: LoginUser
