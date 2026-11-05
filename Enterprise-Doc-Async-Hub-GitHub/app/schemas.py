from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    party_a: str | None
    contract_amount: str | None = Field(pattern=r"^\d+(\.\d{1,2})?$")
    currency: str | None


class TaskView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    filename: str
    md5: str
    status: Literal["PENDING", "QUEUED", "PROCESSING", "RETRY", "SUCCESS", "FAILURE"]
    attempts: int
    result: dict | None
    error: str | None
    created_at: float
    updated_at: float
    history: list


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer_label: str = Field(min_length=1, max_length=80)
    decision: Literal["APPROVE", "REJECT"]
    note: str = Field(min_length=1, max_length=2000)
    corrections: ContractFields | None = None
    task_updated_at: float


class ReviewView(ReviewRequest):
    model_config = ConfigDict(from_attributes=True)
    id: str
    task_id: str
    created_at: float
