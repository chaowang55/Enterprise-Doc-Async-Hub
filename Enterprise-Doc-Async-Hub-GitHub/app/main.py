import hashlib
import hmac
import os
import time
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import get_settings
from app.db import session_factory
from app.models import DocumentReview, DocumentTask, transition
from app.schemas import ReviewRequest, ReviewView, TaskView


def authorize(authorization: str | None = Header(default=None)):
    token = get_settings().api_token
    if token and not hmac.compare_digest(authorization or "", f"Bearer {token}"):
        raise HTTPException(401, "需要有效的 Bearer Token")


app = FastAPI(title="Enterprise Doc Async Hub", version="0.1.0")


@app.middleware("http")
async def timing(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.6f}"
    return response


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(Path(__file__).parent / "static" / "dashboard.html")


@app.get("/health")
def health():
    try:
        with session_factory()() as db:
            db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(503, "数据库尚未就绪") from None
    return {"status": "ok", "llm_mode": get_settings().llm_mode}


@app.post("/api/tasks", status_code=202, dependencies=[Depends(authorize)])
def upload_document(file: Annotated[UploadFile, File()]):
    settings = get_settings()
    filename = (file.filename or "document").replace("\\", "/").split("/")[-1][:255]
    suffix = Path(filename).suffix.lower()
    if suffix not in {".txt", ".pdf", ".docx"}:
        raise HTTPException(415, "仅支持 TXT、PDF、DOCX")
    task_id = str(uuid.uuid4())
    directory = settings.storage_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f"{task_id}.part"
    target = directory / f"{task_id}{suffix}"
    md5, sha256 = hashlib.md5(usedforsecurity=False), hashlib.sha256()
    size = 0
    stored = False
    try:
        with temporary.open("xb") as stream:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, "文件超过上传大小限制")
                md5.update(chunk)
                sha256.update(chunk)
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        if size == 0:
            raise HTTPException(400, "不能上传空文件")
        fingerprint = (md5.hexdigest(), sha256.hexdigest())
        with session_factory()() as db:
            query = select(DocumentTask).where(DocumentTask.md5 == fingerprint[0],
                                                DocumentTask.sha256 == fingerprint[1])
            existing = db.scalar(query)
            if existing:
                return {"task_id": existing.id, "duplicate": True,
                        "status_url": f"/api/tasks/{existing.id}"}
            os.replace(temporary, target)
            task = DocumentTask(id=task_id, filename=filename, path=str(target),
                                md5=fingerprint[0], sha256=fingerprint[1], attempts=0,
                                history=[], status="PENDING")
            transition(task, "PENDING")
            db.add(task)
            try:
                db.commit()
                stored = True
            except IntegrityError:
                db.rollback()
                existing = db.scalar(query)
                if existing is None:
                    raise
                return {"task_id": existing.id, "duplicate": True,
                        "status_url": f"/api/tasks/{existing.id}"}
        return {"task_id": task_id, "duplicate": False, "status_url": f"/api/tasks/{task_id}"}
    finally:
        temporary.unlink(missing_ok=True)
        if not stored:
            target.unlink(missing_ok=True)


@app.get("/api/tasks/{task_id}", response_model=TaskView, dependencies=[Depends(authorize)])
def get_task(task_id: uuid.UUID):
    with session_factory()() as db:
        task = db.get(DocumentTask, str(task_id))
        if task is None:
            raise HTTPException(404, "任务不存在")
        return TaskView.model_validate(task)


@app.post("/api/tasks/{task_id}/reviews", response_model=ReviewView, status_code=201,
          dependencies=[Depends(authorize)])
def create_review(task_id: uuid.UUID, body: ReviewRequest):
    with session_factory().begin() as db:
        task = db.scalar(select(DocumentTask).where(
            DocumentTask.id == str(task_id)).with_for_update())
        if task is None:
            raise HTTPException(404, "任务不存在")
        if task.status != "SUCCESS" or task.updated_at != body.task_updated_at:
            raise HTTPException(409, "任务尚未完成或结果版本已变化，请重新查询")
        review = DocumentReview(id=str(uuid.uuid4()), task_id=task.id,
                                **body.model_dump())
        db.add(review)
        db.flush()
        return ReviewView.model_validate(review)


@app.get("/api/tasks/{task_id}/reviews", response_model=list[ReviewView],
         dependencies=[Depends(authorize)])
def list_reviews(task_id: uuid.UUID):
    with session_factory()() as db:
        if db.get(DocumentTask, str(task_id)) is None:
            raise HTTPException(404, "任务不存在")
        reviews = db.scalars(select(DocumentReview).where(
            DocumentReview.task_id == str(task_id)).order_by(DocumentReview.created_at)).all()
        return [ReviewView.model_validate(review) for review in reviews]
