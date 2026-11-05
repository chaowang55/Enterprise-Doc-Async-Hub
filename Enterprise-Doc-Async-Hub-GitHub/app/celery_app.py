from celery import Celery
from kombu import Queue

from app.config import get_settings


def create_celery():
    settings = get_settings()
    celery = Celery("doc_hub", broker=settings.celery_broker_url,
                    backend=settings.celery_result_backend, include=["app.tasks"])
    celery.conf.update(
        task_serializer="json", result_serializer="json", accept_content=["json"],
        task_default_queue="documents", task_queues=(Queue("documents", durable=True),),
        task_default_delivery_mode="persistent", task_acks_late=True,
        task_reject_on_worker_lost=True, worker_prefetch_multiplier=1,
        task_ignore_result=False, task_track_started=True, result_expires=86400,
        broker_connection_retry_on_startup=True,
        broker_transport_options={"confirm_publish": True},
        task_soft_time_limit=210, task_time_limit=240,
        broker_connection_timeout=3, task_publish_retry=False,
    )
    return celery


celery_app = create_celery()
