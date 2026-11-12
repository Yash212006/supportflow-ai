"""Background reconciliation for refunds whose PayPal outcome is not yet known.

Actions in PENDING_CONFIRMATION (PayPal PENDING, a timeout, or an unreadable response) are re-checked
by re-sending the identical refund request with the same PayPal-Request-Id (or by reading the refund
when its id is known). PayPal returns the original refund, so this can never create a second refund.

Run:  python -m app.workers.reconcile            # loop every RECONCILE_INTERVAL_SECONDS (default 120)
      python -m app.workers.reconcile --once     # single pass
"""

from __future__ import annotations

import logging
import os
import sys
import time

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import ExecutionAction
from app.models.enums import ActionState, ActionType
from app.workflows.execution_engine import ExecutionEngine

log = logging.getLogger("supportflow.reconcile")


def run_once(limit: int = 50) -> dict[str, int]:
    stats = {"checked": 0, "resolved": 0, "still_pending": 0, "errors": 0}
    if not get_settings().paypal_configured:
        log.info("PayPal is not configured; nothing to reconcile")
        return stats
    with SessionLocal() as db:
        ids = db.scalars(
            select(ExecutionAction.id)
            .where(ExecutionAction.state == ActionState.PENDING_CONFIRMATION, ExecutionAction.action_type == ActionType.INITIATE_REFUND)
            .order_by(ExecutionAction.updated_at)
            .limit(limit)
        ).all()
    for action_id in ids:
        with SessionLocal() as db:
            action = db.get(ExecutionAction, action_id)
            if action is None or action.state != ActionState.PENDING_CONFIRMATION:
                continue
            stats["checked"] += 1
            try:
                ExecutionEngine(db).reconcile(action, actor="system:reconciler")
                db.refresh(action)
                stats["still_pending" if action.state == ActionState.PENDING_CONFIRMATION else "resolved"] += 1
            except Exception as exc:  # keep going; the action stays PENDING_CONFIRMATION and is retried next pass
                db.rollback()
                stats["errors"] += 1
                log.warning("reconcile failed for action %s: %s", action_id, type(exc).__name__)
    log.info("reconcile pass: %s", stats)
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if "--once" in sys.argv:
        run_once()
        return
    interval = int(os.environ.get("RECONCILE_INTERVAL_SECONDS", "120"))
    while True:
        run_once()
        time.sleep(interval)


if __name__ == "__main__":
    main()
