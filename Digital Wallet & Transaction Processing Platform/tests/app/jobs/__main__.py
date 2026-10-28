import argparse

from app.database import SessionLocal
from app.jobs import tasks


TASKS = {
    "reset-daily-limits": tasks.reset_daily_limits,
    "cleanup-pending": tasks.cleanup_pending_transactions,
    "scan-suspicious": tasks.scan_suspicious_transactions,
    "daily-wallet-summary": tasks.create_daily_wallet_summary,
    "retry-failed": tasks.retry_failed_transactions,
    "daily-report": tasks.daily_transaction_report,
    "process-approved-refunds": tasks.process_approved_refunds,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a scheduled wallet maintenance task.")
    parser.add_argument("task", choices=TASKS)
    name = parser.parse_args().task
    with SessionLocal() as db:
        print(TASKS[name](db))


if __name__ == "__main__":
    main()
