from typing import Optional

from paper_admin.monkey_patch import MonkeyPatchMeta, get_original
from redis import Redis
from rq.results import Result
from rq.utils import as_text, decode_redis_hash


class PatchResult(Result, metaclass=MonkeyPatchMeta):
    def __init__(self, *args, stdout: Optional[str] = None, **kwargs):
        self.stdout = stdout
        get_original(Result)(self, *args, **kwargs)

    @classmethod
    def create(cls, job, type, ttl, return_value=None, exc_string=None, pipeline=None):
        result = cls(
            job_id=job.id,
            type=type,
            connection=job.connection,
            stdout=getattr(job, "stdout", None),
            return_value=return_value,
            exc_string=exc_string,
            serializer=job.serializer,
        )
        result.save(ttl=ttl, pipeline=pipeline)
        return result

    @classmethod
    def create_failure(cls, job, ttl, exc_string, pipeline=None):
        result = cls(
            job_id=job.id,
            type=cls.Type.FAILED,
            connection=job.connection,
            stdout=getattr(job, "stdout", None),
            exc_string=exc_string,
            serializer=job.serializer,
        )
        result.save(ttl=ttl, pipeline=pipeline)
        return result

    def serialize(self):
        data = get_original(Result)(self)
        if self.stdout is not None:
            data["stdout"] = self.stdout
        return data

    @classmethod
    def restore(cls, job_id: str, result_id: str, payload: dict, connection: Redis, serializer=None) -> 'Result':
        payload = decode_redis_hash(payload)
        result = get_original(Result)(job_id, result_id, payload, connection=connection, serializer=serializer)
        stdout = payload.get("stdout")
        if stdout is not None:
            result.stdout = as_text(stdout)
        return result

