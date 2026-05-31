from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


import app.models.audit  # noqa: E402,F401
import app.models.campaign  # noqa: E402,F401
import app.models.campaign_assignment  # noqa: E402,F401
import app.models.campaign_zone  # noqa: E402,F401
import app.models.driver  # noqa: E402,F401
import app.models.organization  # noqa: E402,F401
import app.models.trip  # noqa: E402,F401
import app.models.user  # noqa: E402,F401
import app.models.vehicle  # noqa: E402,F401
