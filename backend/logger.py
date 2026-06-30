"""
Structured JSON logger.

Every event is emitted as a single JSON line to stdout so it can be
ingested by any log aggregator (Datadog, CloudWatch, etc.) without
any additional configuration.

Usage:
    from logger import log
    log("job.launched", job_id="abc123", provider="runpod-a100-us-east")
"""

import json
import sys
import time
from datetime import datetime, timezone


_LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}
_MIN_LEVEL = "DEBUG"


def _rank(level: str) -> int:
    return _LEVEL_RANK.get(level.upper(), 1)


def log(event: str, level: str = "INFO", **fields):
    if _rank(level) < _rank(_MIN_LEVEL):
        return
    record = {
        "ts":    datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "event": event,
        **fields,
    }
    print(json.dumps(record), file=sys.stdout, flush=True)


def debug(event: str, **kw): log(event, level="DEBUG", **kw)
def info(event: str, **kw):  log(event, level="INFO",  **kw)
def warn(event: str, **kw):  log(event, level="WARN",  **kw)
def error(event: str, **kw): log(event, level="ERROR", **kw)
