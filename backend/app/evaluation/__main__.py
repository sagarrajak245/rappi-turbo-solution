import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

import httpx

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import get_settings
from app.core.db import (
    Base,
    DbConfig,
    DbMode,
    create_engine,
    create_sessionmaker,
    dispose_engine,
    get_sessionmaker,
)
from app.modules.evaluation.runner import run_evaluation


async def _run(live: bool, repeat: int) -> int:
    settings = get_settings()
    # The scenario is seeded into a throwaway SQLite file so the real database is never touched
    # by seed data; only the evaluation run and its results are persisted there.
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite+aiosqlite:///{(Path(tmp) / 'eval.db').as_posix()}"
        engine = create_engine(DbConfig(url=url, mode=DbMode.SQLITE))
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with httpx.AsyncClient() as http:
                out = await run_evaluation(
                    create_sessionmaker(engine),
                    get_sessionmaker(),
                    settings,
                    live=live,
                    repeat=repeat,
                    http=http,
                )
        finally:
            await engine.dispose()
            await dispose_engine()
    for r in out.results:
        print(f"{'PASS' if r.passed else 'FAIL'} {r.case_id}: expected {r.expected} got {r.actual}")
    print(json.dumps({"eval_run_id": out.id, "mode": out.mode, **out.summary}, indent=2))
    return 0 if out.summary["hard_violations"] == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.evaluation")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run a scenario's cases through the agent")
    run.add_argument("--scenario", type=int, default=1, choices=[1])
    run.add_argument("--live", action="store_true", help="use the configured LLM providers")
    run.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.live, args.repeat))


if __name__ == "__main__":
    sys.exit(main())
