import random
import time
from datetime import timedelta

import django_rq
from django.core.management.base import BaseCommand
from rq import get_current_job


def sleep_task(delay):
    time.sleep(delay)


def generate_random_number():
    return random.randint(1, 100)


def pow_number():
    current_job = get_current_job()
    return current_job.dependency.result ** 2


class Command(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, *kwargs)
        self.default_queue = django_rq.get_queue("default")
        self.low_queue = django_rq.get_queue("low")

    def create_sleep_tasks(self):
        for _ in range(5):
            self.default_queue.enqueue(sleep_task, 2)

        for _ in range(3):
            self.low_queue.enqueue(sleep_task, 2)

    def create_deferred_tasks(self):
        for _ in range(5):
            job = self.default_queue.enqueue(generate_random_number)
            self.default_queue.enqueue(pow_number, depends_on=job)

        for _ in range(3):
            job = self.default_queue.enqueue(generate_random_number)
            self.low_queue.enqueue(pow_number, depends_on=job)

    def create_scheduled_tasks(self):
        """
        Uses rq.Scheduler
        """
        for _ in range(5):
            self.default_queue.enqueue_in(timedelta(seconds=60), sleep_task, 2)

        for _ in range(3):
            self.low_queue.enqueue_in(timedelta(seconds=60), sleep_task, 2)

    def create_rq_scheduled_tasks(self):
        """
        Uses rq-scheduler
        """
        scheduler = django_rq.get_scheduler("default")

        for _ in range(3):
            scheduler.enqueue_in(timedelta(seconds=60), sleep_task, 2)

    def handle(self, *args, **options):
        self.create_sleep_tasks()
        self.create_deferred_tasks()
        # self.create_scheduled_tasks()
        self.create_rq_scheduled_tasks()
