import io
import sys

from rq.job import Job as DefaultJob
from rq.utils import as_text, decode_redis_hash


class Job(DefaultJob):
    """
    Подкласс задачи, сохраняющей стандартный вывод
    в новое поле `stdout`.
    """
    def __init__(self, *args, **kwargs):
        self._stdout = None
        super().__init__(*args, **kwargs)

    @property
    def stdout(self):
        if self.supports_redis_streams:
            if not self._cached_result:
                self._cached_result = self.latest_result()

            if self._cached_result:
                return getattr(self._cached_result, "stdout", None)

        if self._stdout is None:
            rv = self.connection.hget(self.key, "stdout")
            if rv is not None:
                self._stdout = as_text(rv)
        return self._stdout

    def _execute(self):
        stdout_buffer = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = stdout_buffer
        try:
            return super()._execute()
        finally:
            sys.stdout = old_stdout
            self._stdout = stdout_buffer.getvalue()

    def to_dict(self, *args, **kwargs) -> dict:
        obj = super().to_dict(*args, **kwargs)
        if self._stdout is not None:
            obj["stdout"] = self._stdout
        return obj
    
    def restore(self, raw_data):
        super().restore(raw_data)
        obj = decode_redis_hash(raw_data)
        self._stdout = obj.get("stdout")
