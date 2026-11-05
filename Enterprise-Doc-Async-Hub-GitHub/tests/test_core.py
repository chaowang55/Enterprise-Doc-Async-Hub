from unittest.mock import Mock

import pytest

from app.db import session_factory
from app.dispatcher import dispatch_once
from app.llm import TransientLLMError
from app.models import DocumentTask
from app.tasks import process_document


def submit(client, content=b"contract", filename="contract.txt"):
    response = client.post("/api/tasks", files={"file": (filename, content)})
    assert response.status_code == 202, response.text
    return response.json()["task_id"]


def due(task_id):
    with session_factory().begin() as db:
        task = db.get(DocumentTask, task_id)
        task.next_run_at = 0
        task.lease_until = 0


def test_upload_deduplicates_and_cleans_files(client, environment):
    first = submit(client)
    response = client.post("/api/tasks", files={"file": ("other.txt", b"contract")})
    assert response.json()["duplicate"] is True
    assert response.json()["task_id"] == first
    assert len(list((environment / "uploads").iterdir())) == 1


def test_timeout_three_retries_then_next_job_runs(client, monkeypatch):
    failed = submit(client)
    extractor = Mock(side_effect=TransientLLMError("timeout"))
    monkeypatch.setattr("app.tasks.extract_contract", extractor)
    for attempt in range(1, 5):
        due(failed)
        dispatch_once(Mock())
        process_document(failed)
        task = client.get(f"/api/tasks/{failed}").json()
        assert task["attempts"] == attempt
        assert task["status"] == ("RETRY" if attempt < 4 else "FAILURE")
    due(failed)
    assert dispatch_once(Mock()) == 0
    process_document(failed)
    assert extractor.call_count == 4
    healthy = submit(client, b"another contract")
    extractor.side_effect = None
    extractor.return_value = {"fields": {"party_a": "B"}}
    dispatch_once(Mock())
    process_document(healthy)
    assert client.get(f"/api/tasks/{healthy}").json()["status"] == "SUCCESS"


def test_publish_failure_keeps_durable_outbox(client):
    task_id = submit(client)
    with pytest.raises(ConnectionError):
        dispatch_once(Mock(side_effect=ConnectionError("broker down")))
    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "PENDING"
    assert dispatch_once(Mock()) == 1
