from typing import Any

from sqlalchemy.dialects.postgresql.base import ischema_names
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import UserDefinedType


class PostGISGeometry(UserDefinedType):
    cache_ok = True

    def __init__(
        self,
        geometry_type: str = "Geometry",
        srid: int | str | None = None,
    ) -> None:
        self.geometry_type = geometry_type
        self.srid = int(srid) if srid is not None else None

    def get_col_spec(self, **_: Any) -> str:
        if self.srid is None:
            return f"geometry({self.geometry_type})"
        return f"geometry({self.geometry_type},{self.srid})"


@compiles(PostGISGeometry, "sqlite")
def compile_sqlite_geometry(_: PostGISGeometry, __, **___: Any) -> str:
    return "TEXT"


ischema_names["geometry"] = PostGISGeometry


class JSONEmptyObjectServerDefault(ColumnElement):
    inherit_cache = True


@compiles(JSONEmptyObjectServerDefault)
def compile_json_empty_object_default(_, __, **___: Any) -> str:
    return "'{}'"


@compiles(JSONEmptyObjectServerDefault, "postgresql")
def compile_postgresql_json_empty_object_default(_, __, **___: Any) -> str:
    return "'{}'::json"


class Base(DeclarativeBase):
    pass


import app.models.assignment_activity  # noqa: E402,F401
import app.models.audience_delivery  # noqa: E402,F401
import app.models.audit  # noqa: E402,F401
import app.models.billing  # noqa: E402,F401
import app.models.campaign  # noqa: E402,F401
import app.models.campaign_assignment  # noqa: E402,F401
import app.models.campaign_cancellation  # noqa: E402,F401
import app.models.campaign_change  # noqa: E402,F401
import app.models.campaign_zone  # noqa: E402,F401
import app.models.contact  # noqa: E402,F401
import app.models.data_purge  # noqa: E402,F401
import app.models.data_subject_request  # noqa: E402,F401
import app.models.disbursement  # noqa: E402,F401
import app.models.disclosure  # noqa: E402,F401
import app.models.driver  # noqa: E402,F401
import app.models.driver_application  # noqa: E402,F401
import app.models.evidence_verification  # noqa: E402,F401
import app.models.exposure_score  # noqa: E402,F401
import app.models.exposure_segment  # noqa: E402,F401
import app.models.fraud_assessment  # noqa: E402,F401
import app.models.fraud_dispute  # noqa: E402,F401
import app.models.impression  # noqa: E402,F401
import app.models.installation_evidence  # noqa: E402,F401
import app.models.kyc  # noqa: E402,F401
import app.models.measurement  # noqa: E402,F401
import app.models.notification  # noqa: E402,F401
import app.models.organization  # noqa: E402,F401
import app.models.payee  # noqa: E402,F401
import app.models.payout  # noqa: E402,F401
import app.models.report_issuance  # noqa: E402,F401
import app.models.retargeting_source  # noqa: E402,F401
import app.models.retargeting_source_link  # noqa: E402,F401
import app.models.route_replay  # noqa: E402,F401
import app.models.stored_file  # noqa: E402,F401
import app.models.trip  # noqa: E402,F401
import app.models.trip_analytics  # noqa: E402,F401
import app.models.user  # noqa: E402,F401
import app.models.vehicle  # noqa: E402,F401
