"""The seed replaces data, so it only runs against a database that is visibly local."""

from sqlalchemy.engine import make_url

from app.core.db import DbConfig, DbMode

_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


class RemoteSeedRefused(Exception):
    pass


def ensure_seed_target(cfg: DbConfig, *, allow_remote: bool) -> None:
    """SQLite, loopback and compose service names (no dot) are local; others need consent."""
    if cfg.mode is DbMode.SQLITE or allow_remote:
        return
    host = make_url(cfg.url).host or ""
    if host in _LOOPBACK or (host and "." not in host):
        return
    raise RemoteSeedRefused(
        f"Refusing to seed remote database host {host!r}: seeding deletes and rewrites the "
        "scenario's rows. Re-run with --allow-remote if you really mean it."
    )
