"""
Background job: auto-release delivered deals whose window has passed.

Runs inside the API process every AUTO_RELEASE_INTERVAL_SECONDS (default 60; 0 disables it).
It's safe to run in more than one process at once: each release re-checks the deal under a
database row lock, so a deal is never released twice (see tests/test_concurrency.py).
"""
import asyncio
import logging

from app import services
from app.database import SessionLocal

log = logging.getLogger("uvicorn.error")      # piggy-back on uvicorn's logger so lines show up in `docker compose logs`


def run_auto_release_once(session_factory=SessionLocal) -> list[str]:
    with session_factory() as db:
        return services.release_due_transactions(db)


async def auto_release_loop(interval_seconds: int):
    while True:
        try:
            released = await asyncio.to_thread(run_auto_release_once)
            if released:
                log.info("auto-released %d transaction(s): %s", len(released), ", ".join(released))
        except Exception:                      # never let one bad sweep kill the loop
            log.exception("auto-release sweep failed")
        await asyncio.sleep(interval_seconds)
