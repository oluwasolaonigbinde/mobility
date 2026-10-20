from uuid import UUID

from sqlalchemy import select

from app.core.errors import AppError
from app.models.user import User
from app.services.admin_authorization import require_active_admin

REPORT_ACTOR_ID = UUID("c37324b8-dddf-4d83-b923-4975d4569cd9")
REPORT_ACTOR_EMAIL = "report-automation@cardvert.invalid"
REPORT_ACTOR_NAME = "Cardvert report automation"
REPORT_ACTOR_PASSWORD = "!report-automation-disabled"


def is_report_automation_user(user: User | None) -> bool:
    return bool(
        user is not None
        and user.id == REPORT_ACTOR_ID
        and user.email == REPORT_ACTOR_EMAIL
        and user.full_name == REPORT_ACTOR_NAME
        and user.password_hash == REPORT_ACTOR_PASSWORD
        and user.role == "admin"
        and user.status == "disabled"
    )


async def require_report_operator(session, actor_user_id: UUID) -> None:
    if actor_user_id != REPORT_ACTOR_ID:
        await require_active_admin(session, actor_user_id)
        return
    user = await session.scalar(
        select(User)
        .where(User.id == REPORT_ACTOR_ID)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not is_report_automation_user(user):
        raise AppError(
            "REPORT_AUTOMATION_UNAVAILABLE",
            "Automatic report preparation is unavailable",
            status_code=503,
        )
