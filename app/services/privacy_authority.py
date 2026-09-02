from starlette import status

from app.core.config import Settings
from app.core.errors import AppError

_PLACEHOLDERS = {"", "missing", "todo", "tbd", "placeholder", "n/a", "none"}


def require_collection_authority(settings: Settings) -> None:
    if (
        settings.privacy_collection_synthetic_test_mode
        and settings.environment.lower() == "test"
    ):
        return
    legal_reference = settings.privacy_legal_approval_reference.strip().lower()
    if (
        not settings.privacy_collection_live_authorized
        or legal_reference in _PLACEHOLDERS
        or legal_reference.startswith("ext-")
    ):
        raise AppError(
            "PRIVACY_COLLECTION_BLOCKED",
            "Sensitive data collection is unavailable until privacy approval is configured",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
