# Contribution

## Development

#### Setup

1. Clone the repository
    ```shell
    git clone https://github.com/dldevinc/paper-rq
    ```
1. Create a virtualenv
    ```shell
    cd paper-rq
    virtualenv .venv
    ```
1. Activate virtualenv
    ```shell
    source .venv/bin/activate
    ```
1. Install dependencies as well as a local editable copy of the library
    ```shell
    pip install -r ./requirements.txt
    pip install -e .
    ```
1. Run test project

    ```shell
    python3 manage.py migrate
    python3 manage.py loaddata tests/fixtures.json
    ```

    ```shell
    python3 manage.py runserver
    ```

    > Django admin credentials: `admin` / `admin`

#### Pre-Commit Hooks

We use [`pre-commit`](https://pre-commit.com/) hooks to simplify linting
and ensure consistent formatting among contributors. Use of `pre-commit`
is not a requirement, but is highly recommended.

```shell
pip install pre-commit
pre-commit install
```

Commiting will now automatically run the local hooks and ensure that
your commit passes all lint checks.

## Testing

Put some tasks into queue:

```python
import random
import django_rq
from time import sleep

queue = django_rq.get_queue("paper:default")
for _ in range(30):
   queue.enqueue(sleep, random.randint(5, 30))
```

Run the RQ queue:

```shell
python3 manage.py rqworker
```
