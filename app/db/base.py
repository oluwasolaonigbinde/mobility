from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


import app.models.assignment_activity  # noqa: E402,F401
import app.models.audit  # noqa: E402,F401
import app.models.billing  # noqa: E402,F401
import app.models.campaign  # noqa: E402,F401
import app.models.campaign_assignment  # noqa: E402,F401
import app.models.campaign_zone  # noqa: E402,F401
import app.models.data_purge  # noqa: E402,F401
import app.models.disbursement  # noqa: E402,F401
import app.models.disclosure  # noqa: E402,F401
import app.models.driver  # noqa: E402,F401
import app.models.fraud_assessment  # noqa: E402,F401
import app.models.fraud_dispute  # noqa: E402,F401
import app.models.impression  # noqa: E402,F401
import app.models.notification  # noqa: E402,F401
import app.models.organization  # noqa: E402,F401
import app.models.payee  # noqa: E402,F401
import app.models.payout  # noqa: E402,F401
import app.models.retargeting_source  # noqa: E402,F401
import app.models.retargeting_source_link  # noqa: E402,F401
import app.models.route_replay  # noqa: E402,F401
import app.models.trip  # noqa: E402,F401
import app.models.trip_analytics  # noqa: E402,F401
import app.models.user  # noqa: E402,F401
import app.models.vehicle  # noqa: E402,F401
