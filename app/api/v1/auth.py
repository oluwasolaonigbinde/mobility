from fastapi import APIRouter
from starlette import status

from app.api.v1.dependencies import SessionDependency, SettingsDependency
from app.core.errors import AppError
from app.core.security import create_access_token
from app.models.user import UserStatus
from app.schemas.auth import LoginRequest, LoginResponse, LoginUser
from app.services.auth import authenticate_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in with email and password",
    description="Exchange local demo or application credentials for a bearer access token.",
)
async def login(
    payload: LoginRequest,
    session: SessionDependency,
    settings: SettingsDependency,
) -> LoginResponse:
    user = await authenticate_user(session, payload.email, payload.password)
    if user is None:
        raise AppError(
            "INVALID_CREDENTIALS",
            "Invalid email or password",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if user.status in {UserStatus.SUSPENDED.value, UserStatus.DISABLED.value}:
        raise AppError(
            "USER_NOT_ACTIVE",
            "User account is not active",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    token, expires_in = create_access_token(user.id, settings)
    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        user=LoginUser.model_validate(user, from_attributes=True),
    )
