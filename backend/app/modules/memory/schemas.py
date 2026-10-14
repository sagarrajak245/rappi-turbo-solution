"""DTOs for lessons."""

from pydantic import BaseModel, ConfigDict

from app.shared.enums import LessonStatus


class LessonOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    sku: str
    node: str
    text: str
    status: LessonStatus
    source_run_id: str | None
    times_applied: int
