"""Одноразовая read-only диагностика ожидания; probe никогда не исполняется."""

from __future__ import annotations

import importlib
import sys

sys.dont_write_bytecode = True

common_module = importlib.import_module("_common")
date = common_module.date
inside = common_module.inside
load = common_module.load
parser = common_module.parser
root_path = common_module.root_path
run = common_module.run
task_path = common_module.task_path
timestamp = common_module.timestamp
schema_module = importlib.import_module("schema")
policy = schema_module.policy
validate = schema_module.validate


def diagnose(state: dict, now: str) -> tuple[str, str]:
    """Отделяет human gate, failure, blocker, deadline и полезный progress."""
    phase = state["state"]
    if phase in ("waiting_spec_approval", "waiting_plan_approval", "waiting_human"):
        return "human_wait", state["next_action"]
    if state["blocker"]:
        return "blocked", state["blocker"]["next_action"]
    if phase == "failed":
        return "failed", "Проверить причину и выполнить явный recovery"
    wait = state["wait"]
    if wait is None:
        return "normal", state["next_action"]
    observation = wait.get("last_observation") or {}
    if isinstance(observation, dict) and observation.get("result") == "failed":
        return "failed", "Зафиксировать failure операции; не повторять ещё работающий процесс"
    current = date(now)
    if current < date(wait["check_after"]):
        return "normal", "Продолжить независимую работу до check_after"
    if current < date(wait["deadline"]):
        return "due", "Проверить handle/log/result и сохранить наблюдение"
    meaningful = date(state["progress"]["last_progress_at"]) > date(wait["started_at"])
    return (
        ("timeout", "Срок превышен: проверить свежий progress, затем ограниченно продлить")
        if meaningful
        else (
            "stalled",
            "Срок превышен без содержательного progress: проверить ввод, handle и зависимости",
        )
    )


def main() -> dict:
    """Выдаёт JSON/text diagnostics без изменения state и запуска probe."""
    p = parser(__doc__, task=True)
    p.add_argument("--now")
    a = p.parse_args()
    root = root_path(a.root)
    task = task_path(root, a.task)
    config = policy(root)
    state = load(inside(task, "state.yaml"))
    validate(state, root, task, config)
    status, action = diagnose(state, a.now or timestamp())
    code = 1 if status in ("timeout", "stalled", "blocked", "failed") else 0
    return {
        "ok": code == 0,
        "code": code,
        "status": status,
        "suggested_action": action,
        "diagnostics": []
        if not code
        else [
            {
                "rule": "wait." + status,
                "path": str(task),
                "message": status,
                "suggested_action": action,
            }
        ],
    }


if __name__ == "__main__":
    raise SystemExit(run(main))
