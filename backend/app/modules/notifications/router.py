"""List, mark read, and stream (SSE) notifications for the signed-in user."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.errors import AppError
from app.modules.auth.deps import CurrentUser
from app.modules.notifications.schemas import NotificationOut
from app.modules.notifications.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])

KEEPALIVE_S = 15.0


def get_notification_service(request: Request) -> NotificationService:
    svc: NotificationService | None = getattr(request.app.state, "notifications", None)
    if svc is None:
        raise AppError("Notifications are not available")
    return svc


Service = Annotated[NotificationService, Depends(get_notification_service)]


@router.get("")
async def list_notifications(user: CurrentUser, svc: Service) -> list[NotificationOut]:
    return await svc.list_for(user.id)


# Declared before /{id}/read so "stream" is never read as an id.
@router.get("/stream")
async def stream(request: Request, user: CurrentUser, svc: Service) -> StreamingResponse:
    queue = svc.broadcaster.subscribe()

    async def events() -> AsyncIterator[str]:
        try:
            yield ": connected\n\n"
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), KEEPALIVE_S)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if event.get("user_id") in (None, user.id):
                    # Unnamed frames reach EventSource.onmessage; the kind travels in the payload.
                    yield f"data: {json.dumps(event)}\n\n"
        finally:
            svc.broadcaster.unsubscribe(queue)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(events(), media_type="text/event-stream", headers=headers)


@router.post("/{notification_id}/read")
async def mark_read(notification_id: int, user: CurrentUser, svc: Service) -> NotificationOut:
    return await svc.mark_read(notification_id, user.id)
