import logging
import uuid

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ImageJob, JobStatus
from app.queue import image_queue
from app.services.storage import get_storage
from app.worker import process_image_job

logger = logging.getLogger(__name__)
settings = get_settings()


class RestyleJobNotFound(Exception):
    pass


def create_restyle_batch(
    db: Session,
    *,
    extra_styling: str | None,
    photo_bytes: bytes,
    photo_ext: str,
) -> list[ImageJob]:
    """
    Merchant uploaded their own photo — restyle it via Flux Kontext Pro
    (Replicate) into MAX_RESTYLE_VARIATIONS distinct-looking options.
    photo_ext is the *validated* real extension (see jobs.py), never the
    client-supplied filename — avoids trusting user input in a storage path.
    """
    storage = get_storage(settings)
    batch_id = str(uuid.uuid4())

    source_key = storage.build_key(batch_id=batch_id, name="source", ext=photo_ext)
    source_path = storage.save(key=source_key, content=photo_bytes)

    jobs: list[ImageJob] = []
    for variation_index in range(settings.MAX_RESTYLE_VARIATIONS):
        job = ImageJob(
            batch_id=batch_id,
            status=JobStatus.PENDING,
            variation_index=variation_index,
            extra_styling=extra_styling,
            source_image_path=source_path,
        )
        db.add(job)
        jobs.append(job)

    db.commit()
    for job in jobs:
        db.refresh(job)
        image_queue.enqueue(
            process_image_job, job.id, job_timeout=settings.RESTYLE_JOB_TIMEOUT_SECONDS
        )

    return jobs


def select_restyle(db: Session, job_id: int) -> ImageJob:
    """
    Merchant picked their favorite variation from a restyle batch. This does
    not enqueue a new render — restyle output is already full quality — it
    just records the preference and clears any prior selection in the same
    batch.
    """
    chosen = db.get(ImageJob, job_id)
    if chosen is None:
        raise RestyleJobNotFound(f"No restyle job with id {job_id}")

    db.query(ImageJob).filter(
        ImageJob.batch_id == chosen.batch_id,
        ImageJob.is_selected.is_(True),
    ).update({"is_selected": False})

    chosen.is_selected = True
    db.commit()
    db.refresh(chosen)
    return chosen