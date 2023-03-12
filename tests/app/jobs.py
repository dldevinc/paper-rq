import time
import random


def sleep(delay):
    time.sleep(delay)
    return delay


def unstable_sleep(delay):
    time.sleep(delay)
    if random.randint(0, 3) == 2:
        raise RuntimeError("Bad luck...")
    return delay
