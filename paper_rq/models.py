import inspect

from django.db import models
from django.db.models.manager import BaseManager
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django_rq.queues import get_queue
from django_rq.settings import QUEUES_LIST
from rq.exceptions import NoSuchJobError
from rq.job import Job
from rq.queue import Queue
from rq.worker import Worker

from .helpers import get_all_connections, get_all_jobs, get_all_workers
from .list_queryset import ListQuerySet


class QueueManager(BaseManager):
    def all(self):
        queues = ListQuerySet(self.model)
        for index, config in enumerate(QUEUES_LIST):
            obj = self.model(
                name=config["name"],
                order=index
            )
            queues.append(obj)

        return queues

    def get(self, **kwargs):
        pk = kwargs.pop("pk", None)
        if pk is None:
            pk = kwargs.pop("name", None)

        if pk is not None:
            for index, config in enumerate(QUEUES_LIST):
                if pk == config["name"]:
                    return self.model(
                        name=config["name"],
                        order=index
                    )

        raise self.model.DoesNotExist


class QueueModel(models.Model):
    name = models.TextField(_("name"), primary_key=True)
    order = models.PositiveIntegerField(_("order"), default=0)

    objects = QueueManager()

    class Meta:
        managed = False
        verbose_name = _("queue")
        default_permissions = ()
        permissions = [
            ("manage", "Can manage RQ jobs")
        ]

    def __str__(self):
        return self.name

    @cached_property
    def queue(self) -> Queue:
        return get_queue(self.name)

    @property
    def worker_count(self):
        return Worker.count(queue=self.queue)


class WorkerManager(BaseManager):
    def all(self):
        workers = ListQuerySet(self.model)
        for worker in get_all_workers():
            obj = self.model.from_worker(worker)
            workers.append(obj)

        return workers

    def get(self, **kwargs):
        pk = kwargs.pop("pk", None)
        if pk is None:
            pk = kwargs.pop("name", None)

        if pk is not None:
            for worker in get_all_workers():
                if worker.name == pk:
                    return self.model.from_worker(worker)

        raise self.model.DoesNotExist


class WorkerModel(models.Model):
    name = models.TextField(_("name"), primary_key=True)
    birth_date = models.DateTimeField(_("birth date"))
    pid = models.PositiveIntegerField(_("PID"))

    objects = WorkerManager()

    class Meta:
        managed = False
        verbose_name = _("worker")
        default_permissions = ()

    def __str__(self):
        return self.name

    @classmethod
    def from_worker(cls, worker):
        return cls(
            name=worker.name,
            birth_date=worker.birth_date,
            pid=worker.pid
        )

    @cached_property
    def worker(self) -> Worker:
        for worker in get_all_workers():
            if worker.name == self.name:
                return worker

    @property
    def state(self):
        return self.worker.get_state()


class JobManager(BaseManager):
    def all(self):
        jobs = ListQuerySet(self.model)
        for job in get_all_jobs():
            obj = self.model.from_job(job)
            jobs.append(obj)

        return jobs

    def get(self, **kwargs):
        pk = kwargs.pop("pk", None)
        if pk is None:
            pk = kwargs.pop("id", None)

        if pk is not None:
            for job in get_all_jobs():
                if job.id == pk:
                    return self.model.from_job(job)

        raise self.model.DoesNotExist


class JobModel(models.Model):
    id = models.TextField(_("ID"), primary_key=True)
    queue = models.TextField(_("queue"))
    description = models.TextField(_("description"))
    timeout = models.TextField(_("timeout"))
    callable = models.TextField(_("callable"))
    result = models.TextField(_("result"))
    exception = models.TextField(_("exception"))
    meta = models.TextField(_("meta"))
    created_at = models.DateTimeField(_("created at"))
    enqueued_at = models.DateTimeField(_("enqueued at"), null=True)
    ended_at = models.DateTimeField(_("ended at"), null=True)

    objects = JobManager()

    class Meta:
        managed = False
        verbose_name = _("job")
        default_permissions = ()

    def __str__(self):
        return self.id

    @classmethod
    def from_job(cls, job):
        if job.instance:
            if inspect.isclass(job.instance):
                instance_class = job.instance
            else:
                instance_class = job.instance.__class__

            callable = "{}.{}.{}".format(
                instance_class.__module__,
                instance_class.__qualname__,
                job.get_call_string()
            )
        else:
            callable = job.get_call_string()

        return cls(
            id=job.id,
            queue=job.origin,
            description=job.description,
            timeout=_("Infinite") if job.timeout is None else str(job.timeout),
            callable=callable,
            result=job.result,
            exception=job.exc_info,
            meta=job.meta,
            created_at=job.created_at,
            enqueued_at=job.enqueued_at,
            ended_at=job.ended_at,
        )

    @cached_property
    def job(self) -> Job:
        for connection in get_all_connections():
            try:
                return Job.fetch(self.id, connection=connection)
            except NoSuchJobError:
                pass

    @property
    def status(self):
        return self.job.get_status(refresh=False)
