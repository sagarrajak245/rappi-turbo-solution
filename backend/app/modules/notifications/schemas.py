from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str | None
    kind: str
    run_id: str | None
    message: str
    read_at: datetime | None
    created_at: datetime
