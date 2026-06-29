import time
from datetime import datetime, timezone

_audit_entries: list[dict] = []


def log_job_launch(user: str, provider_id: str, job_id: str):
    _audit_entries.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": user,
        "provider_id": provider_id,
        "job_id": job_id,
    })


def get_audit_log() -> list[dict]:
    return list(reversed(_audit_entries))
