# paper-rq
An administrative interface for managing RQ tasks in Paper Admin

[![PyPI](https://img.shields.io/pypi/v/paper-rq.svg)](https://pypi.org/project/paper-rq/)
[![Build Status](https://travis-ci.com/dldevinc/paper-rq.svg?branch=master)](https://travis-ci.org/dldevinc/paper-rq)
[![Software license](https://img.shields.io/pypi/l/paper-rq.svg)](https://pypi.org/project/paper-rq/)

## Compatibility
* `django` >= 2.0
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
