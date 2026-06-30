"""
Job templates — save and relaunch common job configurations.

A template captures: provider_id (optional), priority, budget_limit,
name, and description. Launching from a template passes its settings
as defaults (caller can still override individual fields).
"""

import time
import uuid
from database import save_template, list_templates, get_template, delete_template


def create_template(
    name: str,
    description: str = "",
    provider_id: str | None = None,
    priority: str = "normal",
    budget_limit: float | None = None,
) -> dict:
    tmpl = {
        "id":           str(uuid.uuid4())[:8],
        "name":         name,
        "description":  description,
        "provider_id":  provider_id,
        "priority":     priority,
        "budget_limit": budget_limit,
        "created_at":   time.time(),
    }
    save_template(tmpl)
    return tmpl


def get_all_templates() -> list[dict]:
    return list_templates()


def get_one_template(tmpl_id: str) -> dict | None:
    return get_template(tmpl_id)


def remove_template(tmpl_id: str):
    delete_template(tmpl_id)
