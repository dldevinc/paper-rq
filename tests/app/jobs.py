import random
import time

from paper_rq.decorators import job


@job("paper:default")
def sleep(delay):
    time.sleep(delay)
    return delay


@job("paper:default")
def unstable_sleep(delay):
    time.sleep(delay)
    if random.randint(0, 3) == 2:
        raise RuntimeError("Bad luck...")
    return delay
