"""Periodic jobs. Run from cron / a scheduler:

    python -m app.workers.run_jobs billing        # bill due subscriptions (idempotent)
    python -m app.workers.run_jobs deal-health    # refresh alerts
    python -m app.workers.run_jobs expire         # expire stale quotes + approvals, mark overdue invoices
    python -m app.workers.run_jobs all
"""

import argparse
import json
import logging
from datetime import date

from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.services import approval_service, deal_health_service, invoice_service, quote_service, subscription_service

logger = logging.getLogger("dealflow.jobs")


def run_billing(as_of: date | None = None) -> dict:
    with SessionLocal() as db:
        result = subscription_service.run_recurring_billing(db, as_of)
        overdue = invoice_service.refresh_overdue(db, as_of)
        db.commit()
        result["overdue_marked"] = overdue
        return result


def run_deal_health(as_of: date | None = None) -> dict:
    with SessionLocal() as db:
        result = deal_health_service.run(db, as_of)
        db.commit()
        return result


def run_expiry(as_of: date | None = None) -> dict:
    with SessionLocal() as db:
        quotes = quote_service.expire_stale_quotes(db, as_of)
        approvals = approval_service.expire_stale_requests(db)
        overdue = invoice_service.refresh_overdue(db, as_of)
        db.commit()
        return {"quotes_expired": quotes, "approvals_expired": approvals, "overdue_marked": overdue}


JOBS = {"billing": run_billing, "deal-health": run_deal_health, "expire": run_expiry}


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="DealFlow360 periodic jobs")
    parser.add_argument("job", choices=list(JOBS) + ["all"])
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    args = parser.parse_args()
    names = list(JOBS) if args.job == "all" else [args.job]
    for name in names:
        result = JOBS[name](args.as_of)
        logger.info("job finished", extra={"extra_fields": {"job": name, **{k: v for k, v in result.items() if k != "invoice_numbers"}}})
        print(json.dumps({"job": name, "result": result}, default=str))


if __name__ == "__main__":
    main()
