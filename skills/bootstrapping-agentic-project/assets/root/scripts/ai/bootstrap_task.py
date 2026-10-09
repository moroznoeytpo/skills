"""Создание уникального task workspace без внешнего tracker ID."""

from __future__ import annotations

import datetime as dt
import importlib
import re
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.dont_write_bytecode = True

common_module = importlib.import_module("_common")
atomic = common_module.atomic
inside = common_module.inside
parser = common_module.parser
repository = common_module.repository
root_path = common_module.root_path
run = common_module.run
timestamp = common_module.timestamp
schema_module = importlib.import_module("schema")
LEVELS = schema_module.LEVELS
policy = schema_module.policy
require = schema_module.require
validate = schema_module.validate


def main() -> dict:
    """Создаёт минимальные артефакты уровня и фактическую Git identity."""
    p = parser(__doc__)
    p.add_argument("command", choices=["create"])
    p.add_argument("--title", required=True)
    p.add_argument("--level", choices=sorted(LEVELS), required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--slug")
    p.add_argument("--external-id")
    a = p.parse_args()
    root = root_path(a.root)
    config = policy(root)
    slug = a.slug or re.sub(r"[^a-z0-9]+", "-", a.title.lower()).strip("-") or "task"
    require(
        bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)),
        "task.slug",
        "Нужен lowercase ASCII slug",
        2,
    )
    try:
        zone = ZoneInfo(config.get("timezone", "UTC"))
    except ZoneInfoNotFoundError:
        require(
            False, "policy.timezone", "Timezone недоступна; установите tzdata или задайте UTC", 3
        )
    base = dt.datetime.now(zone).date().isoformat() + "-" + slug
    repo = repository(root)
    tasks = inside(root, ".ai/tasks")
    tasks.mkdir(parents=True, exist_ok=True)
    suffix = 1
    while True:
        name = base + ("" if suffix == 1 else "-" + str(suffix))
        task = inside(root, ".ai/tasks/" + name)
        try:
            task.mkdir()
            break
        except FileExistsError:
            suffix += 1
    now = timestamp()
    approvals = {}
    for kind, needed in (
        ("spec", a.level != "trivial"),
        ("plan", a.level in ("planned", "architectural")),
        ("final", a.level in ("planned", "architectural")),
    ):
        approvals[kind] = (
            {"status": "pending"} if needed else {"status": "not_required", "reason": a.level}
        )
        if needed and kind != "final":
            (task / (kind + ".md")).write_text(
                f"# {a.title}\n\nHARNESS_DRAFT — подготовить {kind} перед согласованием.\n"
            )
    state = {
        "version": 1,
        "revision": 1,
        "task": name,
        "title": a.title,
        "external_id": a.external_id,
        "level": a.level,
        "classification": {"reason": a.reason, "signals": {}, "history": []},
        "state": "created",
        "current_step": None,
        "resume_state": None,
        "created_at": now,
        "updated_at": now,
        "scope": a.title,
        "scope_paths": [],
        "next_action": "Определить признаки, scope и шаги",
        "repository": repo,
        "steps": [],
        "approvals": approvals,
        "verification": {
            "status": "pending",
            "evidence": [],
            "scope_fingerprint": None,
            "limitations": [],
        },
        "review": {"status": "not_required", "mode": None, "reason": "trivial", "evidence": []}
        if a.level == "trivial"
        else {"status": "pending", "mode": "code", "evidence": []},
        "knowledge_update": {
            "status": "pending",
            "impact": dict.fromkeys(
                ("project", "architecture", "adr", "lessons", "agent_rules"), "unknown"
            ),
            "rationale": {},
            "changes": [],
            "notification": None,
        },
        "progress": {
            "last_progress_at": now,
            "last_observed_at": now,
            "last_action": "Задача создана",
        },
        "wait": None,
        "blocker": None,
        "history": [
            {"at": now, "event": "created", "from": None, "to": "created", "reason": a.reason}
        ],
    }
    validate(state, root, task, config)
    atomic(task / "state.yaml", state)
    return {"task": name, "path": str(task), "revision": 1}


if __name__ == "__main__":
    raise SystemExit(run(main))
