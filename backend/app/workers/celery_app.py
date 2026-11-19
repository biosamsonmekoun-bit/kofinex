"""Application Celery (traitements longs : import, OCR, calculs, rapports).

Les tâches métier sont ajoutées dans app/workers/tasks/ au fil des phases.
"""

from celery import Celery

from app.core.config import get_settings

_s = get_settings()

celery_app = Celery("kofinex", broker=_s.celery_broker_url, backend=_s.celery_result_backend,
                    include=["app.workers.import_tasks"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    task_acks_late=True,            # une tâche interrompue est rejouée
    worker_prefetch_multiplier=1,   # traitements lourds : pas de préchargement
    task_track_started=True,
    result_expires=60 * 60 * 24,
    task_time_limit=60 * 30,        # OCR de gros PDF : 30 min maximum
    task_soft_time_limit=60 * 28,
)
