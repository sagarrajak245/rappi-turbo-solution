"""Demo users: Sagar (buyer, Mumbai) and an admin. Idempotent; passwords come from settings/env."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.auth import repository as repo
from app.modules.auth.models import User
from app.modules.auth.security import hash_password, verify_password
from app.shared.enums import UserRole

BUYER_EMAIL = "sagar@rappi.test"
ADMIN_EMAIL = "admin@rappi.test"


async def seed_users(
    session: AsyncSession, settings: Settings, now: datetime | None = None
) -> dict[str, int]:
    created = now or datetime.now(UTC)
    wanted = [
        ("Sagar", BUYER_EMAIL, settings.auth.seed_buyer_password, UserRole.BUYER),
        ("Admin", ADMIN_EMAIL, settings.auth.seed_admin_password, UserRole.ADMIN),
    ]
    added = 0
    for name, email, password, role in wanted:
        existing = await repo.get_by_email(session, email)
        if existing is not None:
            # A changed AUTH__SEED_*_PASSWORD takes effect on the next seed.
            if not verify_password(password, existing.password_hash):
                existing.password_hash = hash_password(password)
            continue
        session.add(
            User(
                id=uuid.uuid4().hex,
                name=name,
                email=email,
                password_hash=hash_password(password),
                role=role,
                branch=settings.app.branch,
                created_at=created,
            )
        )
        added += 1
    await session.commit()
    return {"users": added}
