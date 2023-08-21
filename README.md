# paper-rq

An administrative interface for managing RQ tasks in Paper Admin.

⚠ Default `rq.scheduler` is not supported! Use [rq-scheduler](https://github.com/rq/rq-scheduler) instead.

[![PyPI](https://img.shields.io/pypi/v/paper-rq.svg)](https://pypi.org/project/paper-rq/)
[![Build Status](https://github.com/dldevinc/paper-admin/actions/workflows/release.yml/badge.svg)](https://github.com/dldevinc/paper-rq)
[![Software license](https://img.shields.io/pypi/l/paper-rq.svg)](https://pypi.org/project/paper-rq/)

## Compatibility

-   [`paper-admin`](https://github.com/dldevinc/paper-admin) >= 6.0
-   [`django-rq`](https://github.com/rq/django-rq) >= 2.4
-   `python` >= 3.7

## Installation

Install the latest release with pip:

```shell
pip install paper-rq
```

Add `paper_rq` to your INSTALLED_APPS in django's `settings.py`:

```python
INSTALLED_APPS = (
    # ...
    "paper_rq",
)
```

Add `paper_rq` to your `PAPER_MENU`:

```python
from paper_admin.menu import Item

PAPER_MENU = [
    # ...
    Item(
        app="paper_rq",
        icon="bi-clock-history",
    ),
    # ...
]
```

## Result

[![4d17958f25.png](https://i.postimg.cc/mgzCsHVG/4d17958f25.png)](https://postimg.cc/tsbYd7Lr)

## `job` decorator

The same as RQ's `job` decorator, but it automatically works out
the `connection` argument from RQ_QUEUES. It also respects the
`RQ.DEFAULT_RESULT_TTL` and `RQ.DEFAULT_FAILURE_TTL` settings.

Example:
```python
import time

from paper_rq.decorators import job


@job("paper:default")
def sleep(delay):
    time.sleep(delay)
```

```python
sleep.delay(5)
```

## RQ Scheduler

First, ensure that you have the `rq-scheduler` library installed:

```shell
pip install rq-scheduler
```

If you need to run multiple isolated schedulers on the same server, you should
use the class `paper_rq.scheduler.Scheduler`. This class reads the Redis keys 
from the `RQ` settings:

```python
# settings.py

RQ = {
    "DEFAULT_RESULT_TTL": "7d",
    "DEFAULT_FAILURE_TTL": "30d",
    "SCHEDULER_CLASS": "paper_rq.scheduler.Scheduler",
    "SCHEDULER_LOCK_KEY": "rq:scheduler-1:scheduler_lock",
    "SCHEDULER_JOBS_KEY": "rq:scheduler-1:scheduled_jobs",
}
```
