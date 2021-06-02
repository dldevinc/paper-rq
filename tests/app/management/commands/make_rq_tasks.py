import time
import django_rq
from django.core.management.base import BaseCommand


def sleep_task(delay):
    time.sleep(delay)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("-d", "--delay", type=int, default=10)
        parser.add_argument("-n", "--count", type=int, default=30)

    def handle(self, *args, **options):
        for _ in range(options["count"]):
            django_rq.enqueue(sleep_task, options["delay"])
