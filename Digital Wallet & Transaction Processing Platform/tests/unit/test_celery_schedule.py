from app.workers.celery_app import celery
from app.workers import tasks


def test_beat_schedule_references_registered_tasks():
    expected_tasks = {
        "app.workers.tasks.daily_limit_reset",
        "app.workers.tasks.cleanup_pending",
        "app.workers.tasks.scan_suspicious",
        "app.workers.tasks.wallet_summary",
        "app.workers.tasks.retry_failed",
        "app.workers.tasks.daily_report",
        "app.workers.tasks.process_approved_refunds",
    }

    scheduled_tasks = {
        entry["task"] for entry in celery.conf.beat_schedule.values()
    }
    registered_tasks = {
        task.name
        for task in (
            tasks.daily_limit_reset,
            tasks.cleanup_pending,
            tasks.scan_suspicious,
            tasks.wallet_summary,
            tasks.retry_failed,
            tasks.daily_report,
            tasks.process_refunds,
        )
    }

    assert scheduled_tasks == expected_tasks
    assert registered_tasks == expected_tasks
