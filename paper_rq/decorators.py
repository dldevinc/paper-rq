from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Union

from django.conf import settings
from django_rq import get_queue, get_scheduler

if TYPE_CHECKING:
    from redis import Redis
    from rq.job import Retry

from rq.defaults import DEFAULT_RESULT_TTL
from rq.queue import Queue
from rq.types import JobDependencyType
from rq.utils import backend_class


class job:  # noqa
    """
    The same as RQ's job decorator, but it automatically works out
    the ``connection`` argument from RQ_QUEUES.

    If RQ.DEFAULT_RESULT_TTL setting is set, it is used as default
    for ``result_ttl`` kwarg.

    If RQ.DEFAULT_FAILURE_TTL setting is set, it is used as default
    for ``failure_ttl`` kwarg.
    """
    queue_class = Queue

    def __init__(
        self,
        queue: Optional[Union['Queue', str]] = "default",
        queue_class: Optional['Queue'] = None,
        connection: Optional['Redis'] = None,
        timeout: Optional[int] = None,
        result_ttl: Optional[int] = None,
        ttl: Optional[int] = None,
        failure_ttl: Optional[int] = None,
        description: Optional[str] = None,
        depends_on: Optional[JobDependencyType] = None,
        at_front: bool = False,
        meta: Optional[Dict] = None,
        retry: Optional['Retry'] = None,
        on_failure: Optional[Callable[..., Any]] = None,
        on_success: Optional[Callable[..., Any]] = None,
    ):
        """A decorator that adds a ``delay`` method to the decorated function,
        which in turn creates a RQ job when called. Accepts an optional
        ``queue`` argument that can be either a ``Queue`` instance or a string
        denoting the queue name.  For example::

            ..codeblock:python::

                >>> @job(queue="default")
                >>> def simple_add(x, y):
                >>>    return x + y
                >>> ...
                >>> # Puts `simple_add` function into queue
                >>> simple_add.delay(1, 2)

        Args:
            queue (Optional[Union['Queue', str]], optional): The queue to use, can be the Queue class itself, or the queue name (str)
            queue_class (Optional[Queue], optional): A custom class that inherits from `Queue`. Defaults to None.
            connection (Optional[Redis], optional): Redis Connection. Defaults to None.
            timeout (Optional[int], optional): Function timeout. Defaults to None.
            result_ttl (Optional[int], optional): Result time to live. Defaults to None.
            ttl (Optional[int], optional): Time to live. Defaults to None.
            failure_ttl (Optional[int], optional): Failure time to live. Defaults to None.
            description (Optional[str], optional): The job description. Defaults to None.
            depends_on (Optional[JobDependencyType], optional): The job dependencies. Defaults to None.
            at_front (bool, optional): Whether to enqueue the job at the front. Defaults to False.
            meta (Optional[Dict], optional): Metadata to attach to the job. Defaults to None.
            retry (Optional[Retry], optional): Retry object. Defaults to None.
            on_success (Optional[Callable[..., Any]], optional): Callable for on success. Defaults to None.
            on_failure (Optional[Callable[..., Any]], optional): Callable for on failure. Defaults to None.
        """
        RQ = getattr(settings, "RQ", {})
        default_failure_ttl = RQ.get("DEFAULT_FAILURE_TTL")
        default_result_ttl = RQ.get('DEFAULT_RESULT_TTL')

        self._queue = queue
        self._queue_class = backend_class(self, 'queue_class', override=queue_class)
        self._connection = connection
        self.timeout = timeout
        self.result_ttl = result_ttl or default_result_ttl or DEFAULT_RESULT_TTL
        self.ttl = ttl
        self.failure_ttl = failure_ttl or default_failure_ttl
        self.description = description
        self.depends_on = depends_on
        self.at_front = at_front
        self.meta = meta
        self.retry = retry
        self.on_success = on_success
        self.on_failure = on_failure

    @property
    def queue(self):
        if isinstance(self._queue, str):
            try:
                return get_queue(self._queue)
            except KeyError:
                return self.queue_class(name=self._queue, connection=self._connection)
        else:
            return self._queue

    @property
    def scheduler(self):
        return get_scheduler(name=self.queue.name, queue=self.queue)

    def build_enqueue_params(self, args, kwargs):
        depends_on = kwargs.pop("depends_on", None)
        if not depends_on:
            depends_on = self.depends_on

        at_front = kwargs.pop("at_front", None)
        if at_front is None:
            at_front = self.at_front

        return {
            "args": args,
            "kwargs": kwargs,
            "timeout": self.timeout,
            "result_ttl": self.result_ttl,
            "ttl": self.ttl,
            "failure_ttl": self.failure_ttl,
            "description": self.description,
            "depends_on": depends_on,
            "job_id": kwargs.pop("job_id", None),
            "at_front": at_front,
            "meta": self.meta,
            "retry": self.retry,
            "on_failure": self.on_failure,
            "on_success": self.on_success,
        }

    def __call__(self, f):
        @wraps(f)
        def delay(*args, **kwargs):
            params = self.build_enqueue_params(args, kwargs)
            return self.queue.enqueue_call(f, **params)

        f.delay = delay
        return f
