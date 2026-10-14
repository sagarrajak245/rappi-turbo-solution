"""python -m app.seed scenario1 [--today YYYY-MM-DD] [--allow-remote]

Run `alembic upgrade head` first. Seeds the database chosen by DATABASE_URL (SQLite file if unset).
"""

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, time

from app.core.config import get_settings
from app.core.db import create_engine, create_sessionmaker, resolve_database
from app.seed.guard import RemoteSeedRefused, ensure_seed_target
from app.seed.scenario1 import seed_scenario1

SEEDERS = {"scenario1": seed_scenario1}


async def _run(name: str, today: date, now: datetime, allow_remote: bool) -> dict[str, int]:
    cfg = resolve_database(get_settings())
    ensure_seed_target(cfg, allow_remote=allow_remote)
    engine = create_engine(cfg)
    try:
        async with create_sessionmaker(engine)() as session:
            return await SEEDERS[name](session, today=today, now=now)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.seed")
    parser.add_argument("scenario", choices=sorted(SEEDERS))
    parser.add_argument("--today", type=date.fromisoformat, help="seed as if today were this date")
    parser.add_argument("--allow-remote", action="store_true", help="confirm seeding a remote DB")
    args = parser.parse_args(argv)

    now = datetime.now(UTC)
    if args.today:
        now = datetime.combine(args.today, time(6, 0), tzinfo=UTC)
    today = args.today or now.date()
    try:
        report = asyncio.run(_run(args.scenario, today, now, args.allow_remote))
    except RemoteSeedRefused as exc:
        print(exc, file=sys.stderr)
        return 2
    print(f"Seeded {args.scenario} for {today}: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
