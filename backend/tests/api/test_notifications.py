"""Notifications: persisted, broadcast to live subscribers, written when a run needs the buyer."""

import asyncio
from datetime import UTC, date, datetime

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.main import create_app
from app.modules.agent.llm.fake import ScriptedLlm
from app.modules.agent.models import AgentRun
from app.modules.agent.service import AgentService
from app.modules.auth.seed import BUYER_EMAIL, seed_users
from app.modules.notifications.broadcaster import InMemoryBroadcaster
from app.modules.notifications.models import Notification
from app.modules.notifications.service import NotificationService
from app.seed.scenario1 import seed_scenario1
from app.shared.enums import RunStatus

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)


async def test_broadcaster_delivers_to_every_subscriber_and_stops_after_unsubscribe() -> None:
    hub = InMemoryBroadcaster()
    a, b = hub.subscribe(), hub.subscribe()
    await hub.publish({"kind": "x"})
    assert await asyncio.wait_for(a.get(), 1) == {"kind": "x"}
    assert await asyncio.wait_for(b.get(), 1) == {"kind": "x"}
    hub.unsubscribe(a)
    await hub.publish({"kind": "y"})
    assert a.empty()
    assert await asyncio.wait_for(b.get(), 1) == {"kind": "y"}


async def _run_row(sessionmaker: async_sessionmaker[AsyncSession], run_id: str) -> None:
    async with sessionmaker() as s:
        s.add(
            AgentRun(
                id=run_id,
                sku="COKE-750",
                node_code="BANDRA",
                status=RunStatus.FAILED,
                replans_done=0,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await s.commit()


async def test_notify_persists_and_publishes(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await _run_row(sessionmaker, "run1")
    hub = InMemoryBroadcaster()
    q = hub.subscribe()
    await NotificationService(sessionmaker, hub, clock=lambda: NOW).notify(
        "run1", "awaiting_approval", "ready"
    )
    event = await asyncio.wait_for(q.get(), 1)
    assert event["kind"] == "awaiting_approval"
    async with sessionmaker() as s:
        row = (await s.execute(select(Notification))).scalar_one()
    assert (row.run_id, row.user_id, row.read_at) == ("run1", None, None)


async def test_run_awaiting_approval_creates_a_notification(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as s:
        await seed_scenario1(s, today=TODAY, now=NOW)
    notes = NotificationService(sessionmaker, InMemoryBroadcaster(), clock=lambda: NOW)
    svc = AgentService(
        sessionmaker,
        ScriptedLlm([{"verdict": "ACCEPT", "qty": 800, "reasons": ["matches"]}]),
        ScriptedLlm([{"ok": True, "issues": []}]),
        get_settings(),
        clock=lambda: NOW,
        notify=notes.notify,
    )
    run = await svc.start_run("COKE-750", "BANDRA")
    await svc.drain()
    async with sessionmaker() as s:
        row = (await s.execute(select(Notification))).scalar_one()
    assert (row.kind, row.run_id) == ("awaiting_approval", run.id)


async def test_list_and_mark_read(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as s:
        await seed_users(s, get_settings())
    await _run_row(sessionmaker, "r1")
    notes = NotificationService(sessionmaker, InMemoryBroadcaster(), clock=lambda: NOW)
    await notes.notify("r1", "failed", "boom")
    app = create_app()
    app.state.sessionmaker = sessionmaker
    app.state.notifications = notes
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post(
            "/auth/login",
            json={"email": BUYER_EMAIL, "password": get_settings().auth.seed_buyer_password},
        )
        items = (await c.get("/notifications")).json()
        assert [i["kind"] for i in items] == ["failed"]
        assert items[0]["read_at"] is None
        read = await c.post(f"/notifications/{items[0]['id']}/read")
        assert read.status_code == 200
        assert read.json()["read_at"] is not None
        assert (await c.post("/notifications/9999/read")).status_code == 404
