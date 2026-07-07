"""
SQLite persistence layer.

Jobs are written to disk on creation and every status change so the console
survives process restarts. The in-memory dict in job_engine remains the
source of truth for hot reads; this module handles durable writes and
cold-start replay.

Schema (single table, no ORM — intentional: shows raw SQL knowledge):
  jobs(id, provider_id, provider_name, gpu_type, region, priority,
       price_per_hour, base_price_per_hour, status, started_at,
       cost_so_far, projected_cost, budget_limit, retry_count,
       rerouted_from, template_id, created_at)
"""

import json
import os
import sqlite3
import time
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "console.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id                  TEXT PRIMARY KEY,
    provider_id         TEXT,
    provider_name       TEXT,
    gpu_type            TEXT,
    region              TEXT,
    priority            TEXT NOT NULL DEFAULT 'normal',
    price_per_hour      REAL NOT NULL DEFAULT 0.0,
    base_price_per_hour REAL NOT NULL DEFAULT 0.0,
    status              TEXT NOT NULL DEFAULT 'queued',
    started_at          REAL NOT NULL,
    cost_so_far         REAL NOT NULL DEFAULT 0.0,
    projected_cost      REAL,
    budget_limit        REAL,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    rerouted_from       TEXT,
    template_id         TEXT,
    owner               TEXT NOT NULL DEFAULT 'demo-user',
    created_at          REAL NOT NULL,
    scheduled_at        REAL,
    tags                TEXT
);

CREATE TABLE IF NOT EXISTS job_logs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id    TEXT NOT NULL REFERENCES jobs(id),
    line      TEXT NOT NULL,
    logged_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    provider_id TEXT,
    priority    TEXT NOT NULL DEFAULT 'normal',
    budget_limit REAL,
    created_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_job_logs_job_id ON job_logs(job_id);
"""


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db():
    with _conn() as con:
        con.executescript(_SCHEMA)


def upsert_job(job: dict):
    import json as _json
    with _conn() as con:
        con.execute("""
            INSERT INTO jobs
              (id, provider_id, provider_name, gpu_type, region, priority,
               price_per_hour, base_price_per_hour, status, started_at,
               cost_so_far, projected_cost, budget_limit, retry_count,
               rerouted_from, template_id, owner, created_at, scheduled_at, tags)
            VALUES
              (:id, :provider_id, :provider_name, :gpu_type, :region, :priority,
               :price_per_hour, :base_price_per_hour, :status, :started_at,
               :cost_so_far, :projected_cost, :budget_limit, :retry_count,
               :rerouted_from, :template_id, :owner, :created_at, :scheduled_at, :tags)
            ON CONFLICT(id) DO UPDATE SET
              status              = excluded.status,
              cost_so_far         = excluded.cost_so_far,
              projected_cost      = excluded.projected_cost,
              retry_count         = excluded.retry_count,
              rerouted_from       = excluded.rerouted_from,
              provider_id         = excluded.provider_id,
              provider_name       = excluded.provider_name,
              gpu_type            = excluded.gpu_type,
              region              = excluded.region,
              price_per_hour      = excluded.price_per_hour,
              scheduled_at        = excluded.scheduled_at,
              tags                = excluded.tags
        """, {
            "id":                   job["id"],
            "provider_id":          job.get("provider_id"),
            "provider_name":        job.get("provider_name"),
            "gpu_type":             job.get("gpu_type"),
            "region":               job.get("region"),
            "priority":             job.get("priority", "normal"),
            "price_per_hour":       job.get("price_per_hour", 0.0),
            "base_price_per_hour":  job.get("base_price_per_hour", 0.0),
            "status":               job["status"],
            "started_at":           job["started_at"],
            "cost_so_far":          job["cost_so_far"],
            "projected_cost":       job.get("projected_cost"),
            "budget_limit":         job.get("budget_limit"),
            "retry_count":          job.get("_retry_count", 0),
            "rerouted_from":        job.get("_rerouted_from"),
            "template_id":          job.get("template_id"),
            "owner":                job.get("owner", "demo-user"),
            "created_at":           job.get("created_at", job["started_at"]),
            "scheduled_at":         job.get("scheduled_at"),
            "tags":                 _json.dumps(job.get("tags") or {}),
        })


def append_log(job_id: str, line: str):
    with _conn() as con:
        con.execute(
            "INSERT INTO job_logs (job_id, line, logged_at) VALUES (?, ?, ?)",
            (job_id, line, time.time()),
        )


def load_all_jobs() -> list[dict]:
    """Replay persisted jobs into memory on cold start."""
    with _conn() as con:
        rows = con.execute("SELECT * FROM jobs ORDER BY started_at").fetchall()
        result = []
        for row in rows:
            job = dict(row)
            logs = con.execute(
                "SELECT line FROM job_logs WHERE job_id = ? ORDER BY logged_at",
                (job["id"],)
            ).fetchall()
            job["_logs"] = [r["line"] for r in logs]
            job["_last_log_tick"] = 0.0
            job["_retry_count"] = job.pop("retry_count", 0)
            job["_rerouted_from"] = job.pop("rerouted_from", None)
            job["_gpu_samples"] = []
            job["_preempted"] = False
            job["gpu_util"] = 0
            raw_tags = job.get("tags")
            job["tags"] = json.loads(raw_tags) if raw_tags else {}
            result.append(job)
        return result


# Template CRUD
def save_template(tmpl: dict):
    with _conn() as con:
        con.execute("""
            INSERT INTO templates (id, name, description, provider_id, priority, budget_limit, created_at)
            VALUES (:id, :name, :description, :provider_id, :priority, :budget_limit, :created_at)
            ON CONFLICT(id) DO UPDATE SET
              name = excluded.name, description = excluded.description,
              provider_id = excluded.provider_id, priority = excluded.priority,
              budget_limit = excluded.budget_limit
        """, tmpl)


def list_templates() -> list[dict]:
    with _conn() as con:
        return [dict(r) for r in con.execute("SELECT * FROM templates ORDER BY created_at DESC")]


def get_template(tmpl_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM templates WHERE id = ?", (tmpl_id,)).fetchone()
        return dict(row) if row else None


def delete_template(tmpl_id: str):
    with _conn() as con:
        con.execute("DELETE FROM templates WHERE id = ?", (tmpl_id,))
