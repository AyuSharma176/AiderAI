import os

from celery import Celery

redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
default_queue = os.getenv("CELERY_TASK_DEFAULT_QUEUE", "celery")
celery_app = Celery(
    "supportai",
    broker=redis_url,
    backend=redis_url,
    include=["app.workers.tasks", "app.workers.order_tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_default_queue=default_queue,
    beat_schedule={
        "sync-due-commerce-orders": {
            "task": "orders.sync_due",
            "schedule": 15 * 60,
        }
    },
)
