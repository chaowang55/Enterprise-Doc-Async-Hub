import time

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DocumentTask(Base):
    __tablename__ = "document_tasks"
    __table_args__ = (UniqueConstraint("md5", "sha256", name="uq_content_fingerprint"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    md5: Mapped[str] = mapped_column(String(32))
    sha256: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # A durable outbox: the dispatcher scans due rows; no broker call in the upload API.
    next_run_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    run_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    history: Mapped[list] = mapped_column(JSON, default=list)


def transition(task, status, *, error=None):
    task.status = status
    task.error = error
    task.updated_at = time.time()
    task.history = [*task.history, {"status": status, "at": task.updated_at,
                                    "attempt": task.attempts, "error": error}]


class DocumentReview(Base):
    __tablename__ = "document_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("document_tasks.id"), index=True)
    reviewer_label: Mapped[str] = mapped_column(String(80))
    decision: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text)
    corrections: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    task_updated_at: Mapped[float] = mapped_column(Float)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
