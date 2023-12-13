from django.conf import settings
from django.utils.functional import cached_property
from rq.job import JobStatus
from rq_scheduler.scheduler import Scheduler as DefaultScheduler

from . import helpers


class Scheduler(DefaultScheduler):
    """
    Обертка над планировщиком задач библиотеки rq_scheduler.

    Позволяет явно указать Redis-ключ для запланированных задач.
    Это может быть полезно в тех случаях, когда необходимо запускать
    несколько изолированных планировщиков на одном сервере.

    Получает параметры для очередей как в django_rq.DjangoScheduler.
    """

    @cached_property
    def scheduled_jobs_key(self):
        RQ = getattr(settings, "RQ", {})  # noqa: N806
        return RQ.get("SCHEDULER_JOBS_KEY", "rq:scheduler:scheduled_jobs")

    @cached_property
    def scheduler_lock_key(self):
        RQ = getattr(settings, "RQ", {})  # noqa: N806
        return RQ.get("SCHEDULER_LOCK_KEY", "rq:scheduler:scheduler_lock")

    def _create_job(self, func, args=None, kwargs=None, commit=True,
                    result_ttl=None, ttl=None, id=None, status=JobStatus.SCHEDULED,
                    description=None, queue_name=None, timeout=None, meta=None,
                    depends_on=None, on_success=None, on_failure=None):
        from django_rq.settings import QUEUES

        if args is None:
            args = ()

        if kwargs is None:
            kwargs = {}

        if timeout is None:
            queue_name = queue_name or self.queue_name
            timeout = QUEUES[queue_name].get("DEFAULT_TIMEOUT")

        if result_ttl is None:
            result_ttl = getattr(settings, "RQ", {}).get("DEFAULT_RESULT_TTL")

        # Adds initial status
        job = self.job_class.create(
            func, args=args, connection=self.connection,
            kwargs=kwargs, result_ttl=result_ttl, ttl=ttl, status=status, id=id,
            description=description, timeout=timeout, meta=meta,
            depends_on=depends_on, on_success=on_success, on_failure=on_failure,
        )
        if queue_name:
            job.origin = queue_name
        else:
            job.origin = self.queue_name

        if self.queue_class_name:
            job.meta["queue_class_name"] = self.queue_class_name

        if commit:
            job.save()
        return job

    def enqueue_job(self, job):
        # Исправление ситуации, когда повторяющаяся задача (repeat > 1)
        # существует одновременно в нескольких реестрах.
        queue = self.get_queue_for_job(job)
        if helpers.supports_redis_streams(job.connection):
            with queue.connection.pipeline() as pipe:
                queue.canceled_job_registry.remove(job, pipeline=pipe)
                queue.failed_job_registry.remove(job, pipeline=pipe)
                queue.finished_job_registry.remove(job, pipeline=pipe)
                pipe.execute()
        return super().enqueue_job(job)
