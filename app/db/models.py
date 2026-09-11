import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ImageJob(Base):
    """
    One row per generated image.

    Restyle-only service: one uploaded source photo -> MAX_RESTYLE_VARIATIONS
    rows sharing batch_id + source_image_path, each with a different
    variation_index (-> a different rotated style directive, see
    prompt_builder.RESTYLE_VARIATION_STYLES). The merchant picks a favorite;
    is_selected marks it (enforced unique-per-batch in job_service, not DB).

    The full prompt text is NOT stored — it's fully deterministic from
    (variation_index, extra_styling), so it's rebuilt on demand in the
    worker and logged there for debugging instead of persisted redundantly
    across every row.
    """
    __tablename__ = "image_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(36), default=_uuid, index=True)

    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING, index=True)

    variation_index: Mapped[int] = mapped_column(Integer, default=0)
    extra_styling: Mapped[str | None] = mapped_column(Text, nullable=True)

    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)

    source_image_path: Mapped[str] = mapped_column(String(512))

    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)

    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)