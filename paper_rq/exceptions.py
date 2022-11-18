class UnsupportedJobStatusError(Exception):
    def __init__(self, job_id, status):
        self.job_id = job_id
        self.status = status
        super().__init__()
