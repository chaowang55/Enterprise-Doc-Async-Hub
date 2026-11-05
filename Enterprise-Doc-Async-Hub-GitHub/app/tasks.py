import json
import logging
import time
import uuid

from billiard.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select

from app.agent import verify_contract as extract_contract
from app.celery_app import celery_app
from app.config import get_settings
from app.db import session_factory
from app.llm import TransientLLMError
from app.models import DocumentTask, transition
from app.parser import parse_with_sources as parse_document

logger = logging.getLogger(__name__)


def process_document(task_id: str):
    factory = session_factory()
    settings = get_settings()
    token = str(uuid.uuid4())
    with factory.begin() as db:
        task = db.scalar(select(DocumentTask).where(DocumentTask.id == task_id).with_for_update())
        if task is None or task.status in ("SUCCESS", "FAILURE"):
            return
        now = time.time()
        if task.status == "PROCESSING" and task.lease_until > now:
            return
        if task.status in ("PENDING", "RETRY") and task.next_run_at > now:
            return
        if task.attempts >= settings.max_retries + 1:
            transition(task, "FAILURE", error="任务执行次数达到上限（含 worker 中断）")
            return
        task.attempts += 1
        task.run_token = token
        task.lease_until = now + settings.lease_seconds
        transition(task, "PROCESSING")
        path = task.path
    try:
        result = extract_contract(parse_document(path))
        status, error = "SUCCESS", None
    except (TransientLLMError, SoftTimeLimitExceeded):
        result, status, error = None, "RETRY", "模型超时、限流、服务暂不可用或任务软超时"
    except Exception as exc:  # noqa: BLE001 - terminal boundary for individual documents
        # Terminal failures are persisted and acknowledged; the next queue item can run.
        result, status, error = None, "FAILURE", f"处理失败 ({type(exc).__name__})"
    with factory.begin() as db:
        task = db.scalar(select(DocumentTask).where(DocumentTask.id == task_id).with_for_update())
        if task is None or task.run_token != token:
            return  # An old worker must not overwrite the result of a newer execution.
        if status == "RETRY":
            if task.attempts >= settings.max_retries + 1:
                status = "FAILURE"
            else:
                task.next_run_at = time.time() + min(2 ** task.attempts, 60)
        task.lease_until = 0
        task.result = result
        transition(task, status, error=error)
    logger.info(json.dumps({"event": "document_attempt_finished", "task_id": task_id,
                           "status": status, "attempt": task.attempts,
                           "review_status": (result or {}).get("review_status"),
                           "metrics": (result or {}).get("metrics", {})}, ensure_ascii=False))


@celery_app.task(name="documents.process")
def document_task(task_id: str):
    process_document(task_id)
