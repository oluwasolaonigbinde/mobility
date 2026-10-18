from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignCreative
from app.models.campaign_assignment import CampaignAssignment
from app.models.campaign_change import CampaignChangeRequest
from app.models.complaint import Complaint
from app.models.disbursement import PayoutAutomaticAlert, PayoutBatch, PayoutBatchLine
from app.models.driver_application import DriverApplication
from app.models.evidence_verification import EvidenceVerification
from app.models.fraud_dispute import FraudDispute
from app.models.installation_evidence import InstallationEvidenceSubmission
from app.models.payout import PayoutCorrectionOrder
from app.models.trip import QuarantinedPingBatch
from app.models.trip_analytics import FraudFlag
from app.models.vehicle import Vehicle
from app.services.contacts import list_manual_driver_contact_tasks

# Same source IDs and area membership as the staff work queue. Counts are tasks,
# not unique people/campaigns: one record can legitimately need several actions.
SOURCE_AREAS = {
    "applications": "drivers",
    "cars": "drivers",
    "jobs": "campaigns",
    "trips": "trips",
    "late": "trips",
    "campaigns": "campaigns",
    "artwork": "campaigns",
    "photos": "campaigns",
    "checks": "trips",
    "batches": "money",
    "alerts": "money",
    "corrections": "money",
    "complaints": "support",
    "contacts": "support",
    "disputes": "support",
    "changes": "campaigns",
    "paused": "campaigns",
}


async def admin_badge_summary(session: AsyncSession) -> dict:
    def count(model, *filters):
        return select(func.count()).select_from(model).where(*filters).scalar_subquery()

    failed_line = (
        select(PayoutBatchLine.id)
        .where(
            PayoutBatchLine.batch_id == PayoutBatch.id,
            PayoutBatchLine.status == "failed",
        )
        .correlate(PayoutBatch)
        .exists()
    )
    queries = {
        "applications": count(DriverApplication, DriverApplication.status == "pending"),
        "cars": count(Vehicle, Vehicle.status == "pending"),
        "jobs": count(CampaignAssignment, CampaignAssignment.status == "accepted"),
        "trips": select(func.count(func.distinct(FraudFlag.trip_session_id)))
        .where(FraudFlag.status.in_(["open", "acknowledged"]))
        .scalar_subquery(),
        "late": count(QuarantinedPingBatch, QuarantinedPingBatch.status == "quarantined"),
        "campaigns": count(Campaign, Campaign.status == "pending_review"),
        "artwork": count(CampaignCreative, CampaignCreative.status == "pending_review"),
        "photos": count(
            InstallationEvidenceSubmission,
            InstallationEvidenceSubmission.status == "pending_review",
        ),
        "checks": count(
            EvidenceVerification,
            EvidenceVerification.status == "pending",
            EvidenceVerification.verification_type == "physical_spot_check",
        ),
        "batches": count(
            PayoutBatch,
            or_(
                and_(
                    PayoutBatch.status == "reserved",
                    PayoutBatch.approval_mode == "maker_checker",
                    PayoutBatch.approved_at.is_(None),
                ),
                failed_line,
            ),
        ),
        "alerts": count(PayoutAutomaticAlert, PayoutAutomaticAlert.resolved_at.is_(None)),
        "corrections": count(
            PayoutCorrectionOrder, PayoutCorrectionOrder.status == "pending_approval"
        ),
        "complaints": count(Complaint, Complaint.status == "open"),
        "disputes": count(FraudDispute, FraudDispute.status == "open"),
        "changes": count(CampaignChangeRequest, CampaignChangeRequest.status == "pending_admin"),
        "paused": count(Campaign, Campaign.status == "paused"),
    }
    row = (
        await session.execute(select(*(query.label(key) for key, query in queries.items())))
    ).one()
    counts = {key: int(value) for key, value in row._mapping.items()}
    # Reuse the current-consent/current-phone predicate, including completed_at.
    _, counts["contacts"] = await list_manual_driver_contact_tasks(
        session,
        limit=1,
        offset=0,
        history=False,
        open_only=True,
    )
    areas = {
        area: sum(counts[key] for key in SOURCE_AREAS if SOURCE_AREAS[key] == area)
        for area in set(SOURCE_AREAS.values())
    }
    return {**areas, "total": sum(counts.values()), "source_counts": counts}
