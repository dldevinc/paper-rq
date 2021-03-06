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
    virtualenv env
    ```
1. Activate virtualenv
    ```shell
    source env/bin/activate
    ```
1. Install dependencies as well as a local editable copy of the library
    ```shell
    pip install -r ./requirements.txt
    pip install -e .
    ```

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
Run Django server:
```shell
cd ./tests
python3 manage.py migrate
python3 manage.py createsuperuser
python3 manage.py runserver
```

Put some tasks into queue:
```python
import random
import django_rq
from time import sleep

queue = django_rq.get_queue()
for _ in range(30):
   queue.enqueue(sleep, random.randint(5, 30))
```
