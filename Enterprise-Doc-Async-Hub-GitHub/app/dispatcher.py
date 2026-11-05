"""PostgreSQL-backed outbox and retry scheduler. Run separately from the API."""
import logging
import time

from sqlalchemy import and_, or_, select

from app.celery_app import celery_app
from app.db import session_factory
from app.models import DocumentTask, transition

logger = logging.getLogger(__name__)


def dispatch_once(publish=None) -> int:
    if publish is None:
        def publish(task_id):
            celery_app.send_task("documents.process", args=[task_id], task_id=task_id,
                                 queue="documents", retry=False)
    count = 0
    now = time.time()
    # Publish under row lock. A crash after publish/before commit can redeliver;
    # worker row locking + run tokens make that safe. Never mark sent before publishing.
    with session_factory().begin() as db:
        tasks = db.scalars(select(DocumentTask).where(or_(
            and_(DocumentTask.status.in_(["PENDING", "RETRY"]),
                 DocumentTask.next_run_at <= now),
            and_(DocumentTask.status.in_(["QUEUED", "PROCESSING"]),
                 DocumentTask.lease_until <= now),
        )).order_by(DocumentTask.created_at).limit(10).with_for_update(skip_locked=True)).all()
        for task in tasks:
            publish(task.id)
            task.lease_until = now + 30  # Republish if no worker claims the delivery.
            transition(task, "QUEUED")
            count += 1
    return count


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            dispatch_once()
        except Exception:
            logger.exception("分发失败，数据库记录保留，下轮重试")
        time.sleep(1)


if __name__ == "__main__":
    main()
