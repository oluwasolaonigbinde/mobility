from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import model_validator

if TYPE_CHECKING:
    from app.schemas.campaign_assignments import AssignmentCampaignSummary


class CampaignLifecycleReadMixin:
    if TYPE_CHECKING:
        end_at: datetime | None

    @model_validator(mode="after")
    def derive_campaign_status(self):
        from app.services.campaign_lifecycle import campaign_display_status

        self.status = campaign_display_status(self.status, self.end_at)
        return self


class AssignmentLifecycleReadMixin:
    if TYPE_CHECKING:
        campaign: AssignmentCampaignSummary | None

    @model_validator(mode="after")
    def derive_assignment_status(self):
        end = self.campaign.end_at if self.campaign else None
        end = end.replace(tzinfo=UTC) if end and end.tzinfo is None else end
        if self.status in {"offered", "accepted", "active"} and end and end <= datetime.now(UTC):
            self.status = "finished"
        return self
