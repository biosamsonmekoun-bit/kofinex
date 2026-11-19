"""Tâches Celery de l'importation (lecture du fichier, OCR, normalisation, contrôles)."""

from __future__ import annotations

import logging
import uuid

from app.db.session import service_session
from app.services import imports, ledger
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run(step, job_id: str) -> None:
    jid = uuid.UUID(job_id)
    try:
        with service_session() as db:
            step(db, jid)
    except Exception as exc:  # toute erreur imprévue est consignée sur le job, jamais perdue
        logger.exception("Échec de la tâche d'import %s", job_id)
        with service_session() as db:
            job = db.get(imports.ImportJob, jid)
            if job is not None and job.status in ("parsing", "validating"):
                job.status = "failed"
                job.failure_reason = f"Erreur interne pendant le traitement ({type(exc).__name__})."
        raise


@celery_app.task(name="imports.analyze", acks_late=True, max_retries=0)
def analyze_import_task(job_id: str) -> None:
    _run(imports.analyze_import, job_id)


@celery_app.task(name="imports.process", acks_late=True, max_retries=0)
def process_import_task(job_id: str) -> None:
    _run(imports.process_import, job_id)


@celery_app.task(name="ledger.analyze", acks_late=True, max_retries=0)
def analyze_ledger_task(job_id: str) -> None:
    _run(ledger.analyze_ledger, job_id)


@celery_app.task(name="ledger.process", acks_late=True, max_retries=0)
def process_ledger_task(job_id: str) -> None:
    _run(ledger.process_ledger, job_id)
