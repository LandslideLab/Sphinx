"""Background SLA timeout engine. Applies auto-degradation when deadlines fire."""
from __future__ import annotations

import logging
import threading
import time

from sphinx.config import settings
from sphinx.core.events import TOPIC_REQUESTS, bus
from sphinx.core.services import apply_timeout, find_pending_overdue
from sphinx.db import SessionLocal

logger = logging.getLogger("sphinx.policy")

_stop = threading.Event()
_thread: threading.Thread | None = None


def _tick() -> None:
    with SessionLocal() as db:
        try:
            overdue = find_pending_overdue(db)
            for req in overdue:
                apply_timeout(db, req)
                db.commit()
                logger.info("timeout fired for %s (policy=%s)", req.ref, req.policy_name)
        except Exception:  # noqa: BLE001
            logger.exception("policy engine tick failed")
            db.rollback()


def _loop() -> None:
    interval = max(0.1, settings.scheduler_interval_seconds)
    while not _stop.is_set():
        try:
            _tick()
        finally:
            _stop.wait(interval)


def start() -> threading.Thread:
    global _thread
    if _thread and _thread.is_alive():
        return _thread
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="sphinx-sla-engine", daemon=True)
    _thread.start()
    logger.info("SLA policy engine started (interval=%.1fs)", settings.scheduler_interval_seconds)
    return _thread


def stop() -> None:
    _stop.set()
    if _thread:
        _thread.join(timeout=2)
