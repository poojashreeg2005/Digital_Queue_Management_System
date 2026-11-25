"""Run the server-side queue grace-period scheduler."""

from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from app import app
from services.queue_reentry import process_expired_called_tokens


def sweep_expired_calls():
    with app.app_context():
        process_expired_called_tokens()


def main():
    scheduler = BlockingScheduler()
    scheduler.add_job(
        sweep_expired_calls,
        "interval",
        seconds=10,
        id="student_queue_reentry",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    scheduler.start()


if __name__ == "__main__":
    main()
