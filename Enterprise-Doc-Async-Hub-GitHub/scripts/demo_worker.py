"""Local demo only: SQLite + synchronous task calls, without RabbitMQ/Redis."""
import time

from sqlalchemy import select

from app.db import session_factory
from app.models import DocumentTask
from app.tasks import process_document


def main():
    print("本地演示 worker（不验证 RabbitMQ/Redis 或多 worker 并发）", flush=True)
    while True:
        with session_factory()() as db:
            ids = db.scalars(select(DocumentTask.id).where(
                DocumentTask.status.in_(["PENDING", "RETRY"]),
                DocumentTask.next_run_at <= time.time())).all()
        for task_id in ids:
            process_document(task_id)
        time.sleep(1)


if __name__ == "__main__":
    main()
