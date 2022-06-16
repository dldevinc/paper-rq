from django.conf import settings
from django.utils.functional import cached_property
from rq_scheduler.scheduler import Scheduler as DefaultScheduler


class Scheduler(DefaultScheduler):
    """
    Обертка над планировщиком задач библиотеки rq_scheduler.

    Позволяет явно указать Redis-ключ для запланированных задач.
    Это может быть полезно в тех случаях, когда необходимо запускать
    несколько изолированных планировщиков на одном сервере.
    """

    @cached_property
    def scheduled_jobs_key(self):
        RQ = getattr(settings, "RQ", {})  # noqa: N806
        return RQ.get("SCHEDULER_JOBS_KEY", "rq:scheduler:scheduled_jobs")

    @cached_property
    def scheduler_lock_key(self):
        RQ = getattr(settings, "RQ", {})  # noqa: N806
        return RQ.get("SCHEDULER_LOCK_KEY", "rq:scheduler:scheduler_lock")
