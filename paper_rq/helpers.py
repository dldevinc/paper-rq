from datetime import datetime

import pytz
from django.core.exceptions import ImproperlyConfigured
from django_rq import get_queue, get_scheduler
from django_rq.queues import get_queue_by_index, get_redis_connection
from django_rq.settings import QUEUES_LIST
from rq.compat import as_text
from rq.exceptions import NoSuchJobError
from rq.job import Job, JobStatus
from rq.registry import ScheduledJobRegistry
from rq.utils import utcnow
from rq.worker import Worker


def hashable_dict(dict_value):
    return ",".join(":".join(map(str, pair)) for pair in sorted(dict_value.items()))


def get_all_queues():
    for index, config in enumerate(QUEUES_LIST):
        yield get_queue_by_index(index)


def get_all_connections():
    seen_connections = set()
    for index, config in enumerate(QUEUES_LIST):
        connection = get_redis_connection(config['connection_config'])
        connection_params = hashable_dict(connection.connection_pool.connection_kwargs)
        if connection_params not in seen_connections:
            seen_connections.add(connection_params)
            yield connection


def get_all_workers():
    for connection in get_all_connections():
        yield from Worker.all(connection=connection)


def get_scheduled_jobs():
    """
    Получение задач из rq-scheduler.

    Удаляет запланированные задачи из finished_job_registry и failed_job_registry
    чтобы избежать повторения задачи в интерфейсе администратора.
    """
    for queue in get_all_queues():
        try:
            scheduler = get_scheduler()
        except ImproperlyConfigured:
            continue

        for job in scheduler.get_jobs():
            if job.origin != queue.name:
                continue

            with queue.connection.pipeline() as pipe:
                if job in queue.finished_job_registry:
                    queue.finished_job_registry.remove(job, pipeline=pipe)

                if job in queue.failed_job_registry:
                    queue.failed_job_registry.remove(job, pipeline=pipe)

                # Всем задачам следует иметь статус scheduled, чтобы их
                # можно было найти в интерфейсе администратора.
                if job.get_status(refresh=False) != JobStatus.SCHEDULED:
                    job.set_status(JobStatus.SCHEDULED, pipeline=pipe)

                pipe.execute()

            yield job


def get_all_jobs():
    yield from get_scheduled_jobs()

    for queue in get_all_queues():
        job_ids = queue.get_job_ids()
        yield from queue.job_class.fetch_many(job_ids, connection=queue.connection)

        registries = [
            queue.started_job_registry,
            queue.deferred_job_registry,
            queue.scheduled_job_registry,
            queue.finished_job_registry,
            queue.failed_job_registry,
        ]

        for registry in registries:
            job_ids = registry.get_job_ids()
            yield from registry.job_class.fetch_many(job_ids, connection=registry.connection)


def requeue_job(job: Job):
    """
    Повторный запуск задачи.

    Для задач в статусе failed и finished создаётся новая задача,
    с новый ID и очищенными полями result и exc_info. Это сделано
    для удобства логирования. ID исходной задачи сохраняется
    в meta["original_job"].

    Отложенная задача (со статусом scheduled) перемещается в текущую
    очередь на выполнение.
    """
    queue = get_queue(job.origin)

    if job.is_failed or job.is_finished:
        with queue.connection.pipeline() as pipe:
            job.created_at = utcnow()
            job.meta = {"original_job": job.id}
            job._id = None
            new_job = queue.enqueue_job(job)
            pipe.hdel(new_job.key, "result")
            pipe.hdel(new_job.key, "exc_info")
            pipe.execute()
    elif job.is_scheduled:
        # Перемещение отложенной задачи в очередь на выполнение.
        new_job = queue.enqueue_job(job)
        registry = ScheduledJobRegistry(queue.name, queue.connection)
        registry.remove(job)
    else:
        new_job = job

    return new_job
