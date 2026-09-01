from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PostGISGeometry


class CampaignZoneType(StrEnum):
    TARGET = "target"
    EXCLUSION = "exclusion"
    BONUS = "bonus"


class CampaignZone(Base):
    __tablename__ = "campaign_zones"
    __table_args__ = (
        CheckConstraint(
            "zone_type IN ('target', 'exclusion', 'bonus')",
            name="ck_campaign_zones_zone_type",
        ),
        Index("ix_campaign_zones_campaign_zone_type", "campaign_id", "zone_type"),
        Index("ix_campaign_zones_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    zone_type: Mapped[str] = mapped_column(Text, nullable=False)
    geom: Mapped[str] = mapped_column(
        PostGISGeometry("MultiPolygon", 4326), nullable=False
    )
    zone_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON().with_variant(postgresql.JSONB(), "postgresql"),
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
