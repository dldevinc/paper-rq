# paper-rq
An administrative interface for managing RQ tasks in Paper Admin.

[![PyPI](https://img.shields.io/pypi/v/paper-rq.svg)](https://pypi.org/project/paper-rq/)
[![Build Status](https://travis-ci.com/dldevinc/paper-rq.svg?branch=master)](https://travis-ci.org/dldevinc/paper-rq)
[![Software license](https://img.shields.io/pypi/l/paper-rq.svg)](https://pypi.org/project/paper-rq/)

## Compatibility
* [`paper-admin`](https://github.com/dldevinc/paper-admin) >= 2.0
* [`django-rq`](https://github.com/rq/django-rq) >= 2.4
* `python` >= 3.6

## Installation
Install the latest release with pip:

```shell
pip install paper-rq
```

Add `paper_rq` to your INSTALLED_APPS in django's `settings.py`:

```python
INSTALLED_APPS = (
    # other apps
    "paper_rq",
)
```

Add `paper_rq` to your `PAPER_MENU`:
```python
PAPER_MENU = [
    # ...
    dict(
        app="paper_rq",
        icon="fa fa-fw fa-lg fa-clock-o",
    ),
    # ...
]
```

## Result
[![4d17958f25.png](https://i.postimg.cc/mgzCsHVG/4d17958f25.png)](https://postimg.cc/tsbYd7Lr)
