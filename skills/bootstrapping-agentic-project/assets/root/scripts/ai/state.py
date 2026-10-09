"""Единственная штатная точка мутаций task state с typed events и reconciliation."""

from __future__ import annotations

import copy
import datetime as dt
import importlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

common_module = importlib.import_module("_common")
HarnessError = common_module.HarnessError
atomic = common_module.atomic
date = common_module.date
evidence = common_module.evidence
evidence_hashes = common_module.evidence_hashes
file_hash = common_module.file_hash
fingerprint = common_module.fingerprint
inside = common_module.inside
load = common_module.load
lock = common_module.lock
parser = common_module.parser
repository = common_module.repository
requirements = common_module.requirements
root_path = common_module.root_path
run = common_module.run
task_path = common_module.task_path
timestamp = common_module.timestamp
schema_module = importlib.import_module("schema")
LEVELS = schema_module.LEVELS
STATES = schema_module.STATES
TRANSITIONS = schema_module.TRANSITIONS
WORKING = schema_module.WORKING
approved = schema_module.approved
document_ready = schema_module.document_ready
done = schema_module.done
enum = schema_module.enum
fields = schema_module.fields
policy = schema_module.policy
ready = schema_module.ready
step_current = schema_module.step_current
require = schema_module.require
result_current = schema_module.result_current
review_valid = schema_module.review_valid
validate = schema_module.validate
wait_valid = schema_module.wait_valid

EVENT_FIELDS = {
    "classify": {"level", "reason", "signals"},
    "set_steps": {"steps", "scope_paths", "spec_fingerprint", "plan_fingerprint"},
    "step_started": {"step_id"},
    "step_result": {"step_id", "status", "verification", "evidence"},
    "verification_result": {
        "status",
        "evidence",
        "scope_fingerprint",
        "requirements_fingerprints",
        "limitations",
    },
    "review_result": {
        "status",
        "mode",
        "reviewer",
        "independent",
        "evidence",
        "scope_fingerprint",
        "requirements_fingerprints",
        "findings",
    },
    "approval": {"kind", "status", "source", "scope_fingerprint", "scope_summary", "decided_at"},
    "knowledge_result": {"status", "impact", "rationale", "changes", "notification"},
    "progress_observed": {"observed_at", "observation", "evidence", "meaningful"},
    "wait_started": {
        "kind",
        "step_id",
        "condition",
        "probe",
        "started_at",
        "check_after",
        "deadline",
        "timeout_class",
        "attempts",
        "extensions",
        "last_observation",
        "resume_state",
    },
    "wait_extended": {"new_deadline", "evidence", "reason"},
    "wait_resolved": {"result", "evidence"},
    "blocker_recorded": {
        "step_id",
        "expected",
        "observed",
        "investigation",
        "attempts",
        "likely_cause",
        "next_action",
        "resume_state",
    },
    "blocker_resolved": {"step_id", "resolution", "evidence"},
    "checkpoint": {"summary", "next_action", "evidence"},
}


def step(state: dict, key: int) -> dict:
    """Находит шаг по ID, не создавая неизвестную зависимость."""
    for item in state["steps"]:
        if item["id"] == key:
            return item
    raise HarnessError("step.missing", "Шаг не найден")


def invalidate(state: dict, *, approvals: bool = False) -> None:
    """Помечает зависимые результаты stale, сохраняя прежние записи в history."""
    for kind in ("verification", "review", "knowledge_update"):
        if state[kind]["status"] not in ("pending", "not_required"):
            state[kind]["status"] = "stale"
    if approvals:
        for a in state["approvals"].values():
            if a["status"] == "approved":
                a["status"] = "stale"
    elif state["approvals"]["final"]["status"] == "approved":
        state["approvals"]["final"]["status"] = "stale"


def reconcile(state: dict, root: Path, task: Path, p: dict) -> list[str]:
    """Сверяет checkout, requirements, gates и шаги без запуска побочных операций."""
    repo = repository(root)
    require(
        state["repository"]["checkout"] == repo["checkout"],
        "resume.checkout",
        "Другой checkout: требуется явное соответствие задачи и кода",
    )
    if state["repository"].get("base_commit"):
        from _common import git

        git(root, "merge-base", state["repository"]["base_commit"], "HEAD")
    changes = []
    for name in ("spec", "plan"):
        a = state["approvals"][name]
        if a["status"] == "approved" and (
            not (inside(task, name + ".md")).is_file()
            or a["scope_fingerprint"] != file_hash(inside(task, name + ".md"))
        ):
            a["status"] = "stale"
            if name == "spec" and state["approvals"]["plan"]["status"] == "approved":
                state["approvals"]["plan"]["status"] = "stale"
            invalidate(state)
            changes.append(name + " approval stale")
    for name in ("verification", "review"):
        result = state[name]
        if result["status"] == "passed":
            try:
                result_current(
                    result,
                    state,
                    root,
                    task,
                    p,
                    final=name == "review" and result["mode"] == "final",
                )
            except HarnessError:
                result["status"] = "stale"
                state["approvals"]["final"]["status"] = (
                    "stale"
                    if state["approvals"]["final"]["status"] == "approved"
                    else state["approvals"]["final"]["status"]
                )
                changes.append(name + " stale")
    for s in state["steps"]:
        if s["status"] == "done":
            try:
                evidence(task, s["evidence"])
                require(
                    s.get("evidence_hashes") == evidence_hashes(task, s["evidence"]),
                    "step.evidence_stale",
                    "Evidence шага изменено или ещё не зарегистрировано helper",
                )
                if s.get("scope_fingerprint"):
                    require(
                        s["scope_fingerprint"]
                        == fingerprint(
                            root,
                            {**state, "scope_paths": s.get("scope_paths", state["scope_paths"])},
                            {**p, "knowledge_paths": []},
                        ),
                        "step.stale",
                        "Изменён результат шага",
                    )
            except HarnessError:
                s["status"], s["verification"] = "pending", "stale"
                changes.append("step " + str(s["id"]) + " stale")
    changed = True
    while changed:
        changed = False
        for s in state["steps"]:
            if s["status"] in ("done", "running") and any(
                step(state, d)["status"] not in ("done", "skipped") for d in s["depends_on"]
            ):
                s["status"], s["verification"] = "pending", "stale"
                changed = True
    if (
        changes
        and state["wait"] is None
        and state["blocker"] is None
        and state["state"]
        not in ("created", "specifying", "planning", "waiting_human", "failed", "done")
    ):
        state["state"] = "specifying" if any("approval" in c for c in changes) else "implementing"
        state["wait"], state["blocker"], state["resume_state"] = None, None, None
    state["next_action"] = (
        ("Сверить изменения: " + "; ".join(changes))
        if changes
        else (
            "Проверить сохранённый handle/evidence; не повторять side effects"
            if state["wait"]
            else state["next_action"]
        )
    )
    if changes and state["state"] == "waiting_human":
        state["next_action"] += "; требуется решение человека по сохранённому вопросу"
    return changes


def transition(state: dict, target: str, reason: str, root: Path, task: Path, p: dict) -> None:
    """Проверяет явный переход, approvals и terminal guards перед сменой фазы."""
    source = state["state"]
    enum(target, STATES, "target")
    require(bool(reason.strip()), "transition.reason", "Нужна причина")
    require(source != "done", "transition.terminal", "Done терминален; создайте связанную задачу")
    if target == "failed":
        state["failure_reason"] = reason
    elif source == "failed":
        require(
            target in ("ready", "specifying", "planning"),
            "recovery.target",
            "Недопустимая recovery фаза",
        )
        reconcile(state, root, task, p)
        if target == "ready":
            ready(state, task)
        state["failure_reason"] = None
    elif (
        target == "waiting_human"
        and source in WORKING | {"waiting", "blocked"}
        and not (
            source == "reviewing"
            and state["review"].get("mode") == "final"
            and state["review"]["status"] == "passed"
        )
    ):
        origin = source if source in WORKING else state["resume_state"]
        state["resume_state"] = origin
        state["human_gate"] = {
            "kind": "decision",
            "question": reason,
            "resume_state": origin,
            "id": str(state["revision"] + 1),
            "scope_fingerprint": fingerprint(root, state, p, final=True),
        }
        state["human_decision"] = None
    elif source in ("waiting", "blocked", "waiting_human") and target != "done":
        require(
            target == state["resume_state"]
            or (source == "blocked" and target == "implementing")
            or (
                source == "waiting_human"
                and target in ("specifying", "planning", "implementing", "updating_knowledge")
            ),
            "resume.phase",
            "Вернуться можно только в согласованную фазу",
        )
        require(
            state["wait"] is None or source == "waiting_human",
            "wait.unresolved",
            "Сначала закройте wait с evidence",
        )
        require(
            state["blocker"] is None or target == "implementing",
            "blocker.unresolved",
            "Blocker ещё открыт",
        )
        if source == "waiting_human":
            if state["human_gate"]["kind"] == "final":
                require(
                    state["approvals"]["final"]["status"] == "rejected"
                    and state["approvals"]["final"]["scope_fingerprint"]
                    == fingerprint(root, state, p, final=True),
                    "human.pending",
                    "Нужен отказ человека для текущего final scope",
                )
                invalidate(state)
            else:
                require(
                    state.get("human_decision") is not None
                    and state["human_decision"].get("gate_id") == state["human_gate"].get("id")
                    and state["human_decision"].get("scope_fingerprint")
                    == fingerprint(root, state, p, final=True)
                    and state["human_decision"].get("resume_state") == target,
                    "human.pending",
                    "Нужно решение именно текущего вопроса и scope",
                )
    else:
        require(
            target in TRANSITIONS.get(source, set()),
            "transition.forbidden",
            f"Запрещён {source} → {target}",
        )
        if source == "created" and target == "ready":
            require(state["level"] == "trivial", "level.spec", "Сначала specifying")
        if target == "specifying":
            require(state["level"] != "trivial", "level.trivial", "Trivial не требует spec")
        if target == "waiting_spec_approval":
            document_ready(task, "spec")
        if target == "planning":
            require(
                state["level"] in ("planned", "architectural"),
                "level.plan",
                "Plan не нужен этому уровню",
            )
            approved(state, task, "spec")
        if source == "waiting_spec_approval" and target == "ready":
            require(state["level"] == "bounded", "level.plan", "Нужен plan approval")
        if target == "waiting_plan_approval":
            document_ready(task, "plan")
            approved(state, task, "spec")
        if target in ("ready", "implementing"):
            ready(state, task)
        if source == "implementing" and target == "verifying":
            require(
                any(s["status"] in ("running", "done", "failed") for s in state["steps"]),
                "verify.subject",
                "Нет предмета проверки",
            )
        if source == "verifying" and target in ("reviewing", "updating_knowledge"):
            result_current(state["verification"], state, root, task, p)
            require(
                all(s["status"] in ("done", "skipped") for s in state["steps"]),
                "verify.steps",
                "Шаги ещё не закончены",
            )
            if target == "updating_knowledge":
                require(
                    state["level"] == "trivial" and state["review"]["status"] == "not_required",
                    "review.required",
                    "Сначала review",
                )
        if source == "reviewing" and target == "updating_knowledge":
            require(
                (
                    state["review"]["status"] == "changes_requested"
                    and state["review"]["mode"] == "final"
                )
                or state["review"]["status"] == "passed",
                "review.pending",
                "Нужно code review",
            )
            if state["review"]["status"] == "passed":
                result_current(
                    state["review"], state, root, task, p, final=state["review"]["mode"] == "final"
                )
        if source == "updating_knowledge" and target == "reviewing":
            require(
                state["knowledge_update"]["status"] in ("updated", "no_change"),
                "knowledge.pending",
                "Сначала knowledge check",
            )
            state["review"] = {**state["review"], "status": "pending", "mode": "final"}
        if target == "waiting_human":
            require(state["review"]["mode"] == "final", "review.final", "Требуется final review")
            result_current(state["review"], state, root, task, p, final=True)
            state["human_gate"] = {"kind": "final", "question": reason, "resume_state": "reviewing"}
            state["resume_state"] = "reviewing"
    if target in (
        "ready",
        "implementing",
        "verifying",
        "reviewing",
        "updating_knowledge",
    ) and source in ("waiting", "blocked", "waiting_human", "failed"):
        ready(state, task)
    if target == "done":
        if source == "waiting_human":
            require(
                state.get("human_gate", {}).get("kind") == "final",
                "done.human_kind",
                "Это не final acceptance",
            )
        if source == "updating_knowledge":
            require(
                state["level"] == "trivial" and state["review"]["status"] == "not_required",
                "done.review",
                "Нужно final review",
            )
        done(state, root, task, p)
        state["next_action"] = "Завершено; новая работа создаёт новую связанную задачу"
        state["resume_state"] = None
    if target == "implementing" and source in ("reviewing", "verifying"):
        invalidate(state)
    state["state"] = target


def record(state: dict, name: str, payload: dict, root: Path, task: Path, p: dict) -> None:
    """Обрабатывает только типизированные events в допустимых фазах."""
    require(
        isinstance(name, str) and name in EVENT_FIELDS,
        "event.unknown",
        "Неизвестное событие; arbitrary patch запрещён",
        2,
    )
    fields(payload, EVENT_FIELDS[name], "event.payload")
    require(
        state["state"] not in ("done", "failed"),
        "event.terminal",
        "Терминальная задача не принимает события",
    )
    phase = state["state"]
    # Независимый шаг разрешён во время технического ожидания исполнения.
    executing = phase == "implementing" or (
        phase == "waiting"
        and state["wait"] is not None
        and state["wait"]["resume_state"] == "implementing"
    )
    if name == "classify":
        enum(payload["level"], LEVELS, "level")
        fields(payload["signals"], set(), "classification.signals")
        signals = payload["signals"]
        minimum = (
            "architectural"
            if any(
                signals.get(x)
                for x in (
                    "boundary",
                    "ownership",
                    "security",
                    "concurrency",
                    "infrastructure",
                    "storage",
                    "protocol",
                    "significant_dependency",
                )
            )
            else "planned"
            if any(
                signals.get(x)
                for x in ("api", "schema", "migration", "multiple_components", "dependent_steps")
            )
            else "bounded"
            if any(signals.get(x) for x in ("behavior", "dependency"))
            else "trivial"
        )
        order = ["trivial", "bounded", "planned", "architectural"]
        require(
            order.index(payload["level"]) >= order.index(minimum),
            "classification.minimum",
            "Обнаруженные признаки требуют более высокого уровня",
        )
        if state["level"] != payload["level"]:
            require(
                bool(payload.get("changed_scope")),
                "classification.scope",
                "Нужно объяснение изменения scope",
            )
            if order.index(payload["level"]) < order.index(state["level"]):
                require(
                    bool(payload.get("narrowing_evidence"))
                    and not state.get("pending_architecture"),
                    "classification.downgrade",
                    "Нужно доказанное сужение без нерешённого architecture gate",
                )
            state["classification"]["history"].append(
                copy.deepcopy(state["classification"]) | {"level": state["level"]}
            )
            state["level"] = payload["level"]
            invalidate(state, approvals=True)
            state["state"] = "specifying" if payload["level"] != "trivial" else "created"
            # Операция живёт независимо от смены scope: handle нельзя потерять.
            for operation in (state["wait"], state["blocker"]):
                if operation is not None:
                    operation["resume_state"] = state["state"]
            state["resume_state"] = state["state"] if state["wait"] or state["blocker"] else None
            if payload["level"] != "trivial" and state["review"]["status"] == "not_required":
                state["review"] = {"status": "pending", "mode": "code", "evidence": []}
            for kind in ("spec", "plan", "final"):
                needed = (
                    payload["level"] != "trivial"
                    if kind == "spec"
                    else payload["level"] in ("planned", "architectural")
                )
                if needed and state["approvals"][kind]["status"] == "not_required":
                    state["approvals"][kind] = {"status": "pending"}
        state["classification"].update({"reason": payload["reason"], "signals": signals})
    elif name == "set_steps":
        require(
            phase in ("created", "specifying", "planning"),
            "event.phase",
            "set_steps только в подготовке",
        )
        actual = requirements(task, state["level"])
        require(
            payload["spec_fingerprint"] == actual["spec"]
            and payload["plan_fingerprint"] == actual["plan"],
            "requirements.stale",
            "Укажите текущие spec/plan hashes",
        )
        for operation in (state["wait"], state["blocker"]):
            if operation is not None:
                original = step(state, operation["step_id"])
                require(
                    any(s == original for s in payload["steps"]),
                    "steps.live",
                    "Нельзя заменить шаг незакрытой операции; сохраните его ID/status/dependencies",
                )
        state["steps"], state["scope_paths"] = payload["steps"], payload["scope_paths"]
        invalidate(state, approvals=True)
    elif name == "step_started":
        require(executing, "event.phase", "Запуск шага только при исполнении или его wait")
        ready(state, task)
        s = step(state, payload["step_id"])
        require(
            all(op is None or op["step_id"] != s["id"] for op in (state["wait"], state["blocker"])),
            "step.live",
            "Сначала закройте существующую операцию этого шага",
        )
        for dependency in s["depends_on"]:
            step_current(step(state, dependency), state, root, task, p)
        require(
            s["status"] in ("pending", "failed"),
            "step.start",
            "Шаг уже выполняется/завершён/заблокирован",
        )
        s["status"] = "running"
        state["current_step"] = s["id"]
    elif name == "step_result":
        require(executing or phase == "verifying", "event.phase", "Результат шага вне исполнения")
        s = step(state, payload["step_id"])
        require(s["status"] in ("running", "failed"), "step.result", "Шаг не запускался")
        enum(payload["status"], {"done", "failed", "skipped"}, "step_result.status")
        if payload["status"] == "done":
            evidence(task, payload["evidence"])
            for dependency in s["depends_on"]:
                step_current(step(state, dependency), state, root, task, p)
        s.update({k: payload[k] for k in ("status", "verification", "evidence")})
        if "exception" in payload:
            s["exception"] = payload["exception"]
        if payload["status"] == "done":
            scope = payload.get("scope_paths", state["scope_paths"])
            require(
                isinstance(scope, list) and bool(scope),
                "step.scope",
                "Нужен непустой scope результата",
                2,
            )
            for path in scope:
                inside(root, path)
            s["scope_paths"] = scope
            s["scope_fingerprint"] = fingerprint(
                root, {**state, "scope_paths": scope}, {**p, "knowledge_paths": []}
            )
            s["evidence_hashes"] = evidence_hashes(task, s["evidence"])
    elif name in ("verification_result", "review_result"):
        is_review = name == "review_result"
        require(
            phase == ("reviewing" if is_review else "verifying"),
            "event.phase",
            "Результат не соответствует фазе",
        )
        candidate = copy.deepcopy(payload)
        if is_review:
            expected_mode = (
                "code" if state["review"]["status"] == "not_required" else state["review"]["mode"]
            )
            require(
                candidate["mode"] == expected_mode,
                "review.mode",
                "Mode события должен соответствовать текущему раунду review",
            )
        if candidate["status"] == "passed":
            candidate["evidence_hashes"] = evidence_hashes(task, candidate["evidence"])
            if is_review:
                require((inside(task, "review.md")).is_file(), "review.artifact", "Нужен review.md")
                candidate["review_artifact_hash"] = file_hash(inside(task, "review.md"))
        if candidate["status"] == "passed":
            result_current(
                candidate, state, root, task, p, final=is_review and candidate["mode"] == "final"
            )
            if is_review:
                review_valid(candidate)
                if candidate["mode"] == "final":
                    require(
                        state["knowledge_update"]["status"] in ("updated", "no_change"),
                        "review.knowledge",
                        "Сначала knowledge check",
                    )
                require(
                    (inside(task, "review.md")).is_file(),
                    "review.artifact",
                    "Нужен фактический review.md",
                )
        elif candidate["status"] in ("failed", "blocked", "changes_requested"):
            require(
                bool(
                    candidate.get("reason")
                    or candidate.get("limitations")
                    or candidate.get("findings")
                ),
                "result.reason",
                "Нужна причина неуспеха",
            )
        state["review" if is_review else "verification"] = candidate
    elif name == "approval":
        kind = payload["kind"]
        enum(kind, {"spec", "plan", "final"}, "approval.kind")
        enum(payload["status"], {"approved", "rejected"}, "approval.status")
        require(
            bool(payload["source"]) and bool(payload["scope_summary"]),
            "approval.source",
            "Нужен реальный human source/scope",
        )
        require(
            phase
            in (
                {
                    "created",
                    "specifying",
                    "waiting_spec_approval",
                    "planning",
                    "waiting_plan_approval",
                }
                if kind != "final"
                else {"waiting_human"}
            ),
            "approval.phase",
            "Approval вне соответствующего human gate",
        )
        expected = (
            fingerprint(root, state, p, final=True)
            if kind == "final"
            else file_hash(inside(task, kind + ".md"))
        )
        require(
            payload["scope_fingerprint"] == expected,
            "approval.stale",
            "Approval не для текущего содержимого",
        )
        if kind != "final":
            document_ready(task, kind)
        state["approvals"][kind] = {k: v for k, v in payload.items() if k != "kind"}
        state["human_decision"] = {"source": payload["source"], "status": payload["status"]}
        if kind == "spec" and state["approvals"]["plan"]["status"] == "approved":
            state["approvals"]["plan"]["status"] = "stale"
    elif name == "knowledge_result":
        require(
            phase == "updating_knowledge",
            "event.phase",
            "Knowledge result только после code review",
        )
        state["knowledge_update"] = copy.deepcopy(payload)
    elif name == "progress_observed":
        date(payload["observed_at"])
        require(type(payload["meaningful"]) is bool, "progress.meaningful", "Нужен boolean", 2)
        state["progress"]["last_observed_at"] = payload["observed_at"]
        if payload["meaningful"]:
            evidence(task, payload["evidence"])
            require(
                payload["observation"] != state["progress"]["last_action"],
                "progress.repeat",
                "Повтор сообщения не progress",
            )
            state["progress"]["last_progress_at"] = payload["observed_at"]
            state["progress"]["last_action"] = payload["observation"]
        if state["wait"]:
            state["wait"]["last_observation"] = copy.deepcopy(payload)
    elif name == "wait_started":
        require(
            phase in WORKING and state["wait"] is None, "wait.nested", "Нельзя вложенное waiting"
        )
        require(payload["resume_state"] == phase, "wait.resume", "Нужно сохранить исходную фазу")
        wait_valid(payload, p)
        previous = [
            h["payload"]
            for h in state["history"]
            if h.get("event") == "wait_started"
            and h.get("payload", {}).get("step_id") == payload["step_id"]
        ]
        if previous:
            require(
                payload["attempts"] == previous[-1]["attempts"] + 1
                and bool(payload.get("prior_terminated_evidence")),
                "wait.retry",
                "Retry требует увеличения attempts и evidence завершения прежнего процесса",
            )
            evidence(task, payload["prior_terminated_evidence"])
        state["wait"] = copy.deepcopy(payload)
        state["resume_state"], state["state"] = phase, "waiting"
        step(state, payload["step_id"])["status"] = "waiting"
    elif name == "wait_extended":
        w = state["wait"]
        require(w is not None, "wait.missing", "Нет активного wait")
        evidence(task, payload["evidence"])
        require(
            bool(w["last_observation"])
            and isinstance(w["last_observation"], dict)
            and w["last_observation"].get("meaningful") is True,
            "wait.progress",
            "Нет подтверждённого содержательного прогресса",
        )
        expected = date(w["deadline"]) + dt.timedelta(
            seconds=p["timeouts"][w["timeout_class"]]["deadline_seconds"]
            * p["stall_policy"]["extension_factor"]
        )
        require(
            date(payload["new_deadline"]) == expected,
            "wait.extension",
            "Продление должно соответствовать policy",
        )
        w["deadline"], w["extensions"] = payload["new_deadline"], w["extensions"] + 1
        w["check_after"] = min(
            date(w["deadline"]),
            date(timestamp())
            + dt.timedelta(seconds=p["timeouts"][w["timeout_class"]]["check_every_seconds"]),
        ).isoformat()
        w["last_observation"]["meaningful"] = False
    elif name == "wait_resolved":
        require(state["wait"] is not None, "wait.missing", "Нет активного wait")
        enum(payload["result"], {"completed", "failed", "cancelled"}, "wait.result")
        evidence(task, payload["evidence"])
        reconciliation = reconcile(state, root, task, p)
        w = state["wait"]
        s = step(state, w["step_id"])
        dependencies_current = all(
            step(state, d)["status"] in ("done", "skipped") for d in s["depends_on"]
        )
        target = w["resume_state"]
        if target not in ("created", "specifying", "planning"):
            try:
                ready(state, task)
            except HarnessError:
                target = "specifying" if state["level"] != "trivial" else "created"
        s["status"] = (
            "running"
            if payload["result"] == "completed"
            and dependencies_current
            and target == "implementing"
            and phase != "waiting_human"
            else "pending"
            if payload["result"] == "completed"
            else "failed"
        )
        if s["status"] == "running":
            state["current_step"] = s["id"]
        s["operation_result"] = {
            **copy.deepcopy(payload),
            "probe": w["probe"],
            "evidence_hashes": evidence_hashes(task, payload["evidence"]),
            "reconciliation": reconciliation,
        }
        state["wait"] = None
        if phase != "waiting_human":
            state["state"], state["resume_state"] = target, None
    elif name == "blocker_recorded":
        expected_resume = state["resume_state"] if phase == "waiting" else phase
        require(
            expected_resume in WORKING and payload["resume_state"] == expected_resume,
            "blocker.resume",
            "Blocker обязан сохранять фактическую исходную фазу",
        )
        require(state["blocker"] is None, "blocker.nested", "Нельзя заменить незакрытый blocker")
        require(phase not in ("failed", "done"), "blocker.phase", "Терминальная задача")
        state["blocker"] = copy.deepcopy(payload)
        state["resume_state"] = payload["resume_state"]
        state["state"], state["next_action"] = "blocked", payload["next_action"]
        step(state, payload["step_id"])["status"] = "blocked"
    elif name == "blocker_resolved":
        require(
            state["blocker"] is not None and state["blocker"]["step_id"] == payload["step_id"],
            "blocker.missing",
            "Blocker не найден",
        )
        evidence(task, payload["evidence"])
        step(state, payload["step_id"])["status"] = "pending"
        target = state["resume_state"]
        if phase == "waiting_human":
            state["blocker"] = None
            return
        if target in ("ready", "implementing", "verifying", "reviewing", "updating_knowledge"):
            ready(state, task)
        state["state"], state["resume_state"], state["blocker"] = target, None, None
        if state["wait"] is not None:
            state["state"] = "waiting"
            state["resume_state"] = state["wait"]["resume_state"]
    elif name == "checkpoint":
        state["next_action"] = payload["next_action"]
        if "human_decision" in payload:
            decision = payload["human_decision"]
            fields(
                decision,
                {"source", "decided_at", "gate_id", "scope_fingerprint", "resume_state"},
                "checkpoint.human_decision",
            )
            require(
                phase == "waiting_human"
                and state["human_gate"]["kind"] == "decision"
                and bool(decision["source"])
                and decision["gate_id"] == state["human_gate"].get("id")
                and decision["scope_fingerprint"] == fingerprint(root, state, p, final=True),
                "human.decision",
                "Решение не относится к текущему gate/scope",
            )
            date(decision["decided_at"])
            state["human_decision"] = copy.deepcopy(decision)
        if payload["evidence"]:
            hashes = evidence_hashes(task, payload["evidence"])
            old = [h for h in state["history"] if h.get("event") == "checkpoint"]
            repeated = (
                bool(old)
                and old[-1].get("payload", {}).get("summary") == payload["summary"]
                and state["progress"].get("checkpoint_evidence_hashes") == hashes
            )
            if repeated:
                return
            state["progress"]["checkpoint_evidence_hashes"] = hashes
            state["progress"]["last_progress_at"] = timestamp()
            state["progress"]["last_action"] = payload["summary"]


def main() -> dict:
    """Выполняет read/validate/revision/apply/validate/atomic под коротким lock."""
    p = parser(__doc__, task=True)
    p.add_argument("command", choices=["show", "transition", "record", "resume"])
    p.add_argument("--expected-revision", type=int)
    p.add_argument("--to")
    p.add_argument("--reason", default="Reconciliation реального checkout")
    p.add_argument("--event-file")
    a = p.parse_args()
    root = root_path(a.root)
    config = policy(root)
    task = task_path(root, a.task)
    path = inside(task, "state.yaml")
    if a.command == "show":
        state = load(path)
        validate(state, root, task, config)
        return {
            "state": state,
            "fingerprints": {
                "code": fingerprint(root, state, config),
                "final": fingerprint(root, state, config, final=True),
                "requirements": requirements(task, state["level"]),
            },
        }
    require(a.expected_revision is not None, "cli.revision", "Нужен --expected-revision", 2)
    require(task.is_dir(), "task.missing", "Task directory отсутствует", 3)
    with lock(task):
        state = load(path)
        # Старые YAML aliases могли связать текущие steps с сохранённым payload.
        # Отделяем журнал до мутации, сохраняя его фактическое содержание.
        if "history" in state:
            state["history"] = copy.deepcopy(state["history"])
        if a.expected_revision != state.get("revision"):
            raise HarnessError("write.revision", "Конфликт revision: перечитайте state", 3)
        # Resume должен диагностировать утрату evidence до строгой проверки done steps.
        before = copy.deepcopy(state)
        changes = []
        if a.command == "resume":
            require(
                state.get("state") != "done",
                "resume.terminal",
                "Done проверяется validate; ошибку исправляет явная human-disposition",
            )
            fields(
                state,
                {
                    "repository",
                    "approvals",
                    "steps",
                    "verification",
                    "review",
                    "knowledge_update",
                    "state",
                    "progress",
                    "next_action",
                    "level",
                    "scope_paths",
                },
                "resume state",
            )
            changes = reconcile(state, root, task, config)
        else:
            validate(state, root, task, config)
        name, payload = a.command, {}
        if a.command == "transition":
            require(a.to is not None, "cli.target", "Нужен --to", 2)
            transition(state, a.to, a.reason, root, task, config)
        elif a.command == "record":
            require(a.event_file is not None, "cli.event", "Нужен --event-file", 2)
            try:
                item = json.loads(Path(a.event_file).read_text(encoding="utf-8"))
            except (ValueError, UnicodeError) as error:
                raise HarnessError("event.json", "Невалидный JSON event", 2) from error
            fields(item, {"event", "reason", "payload"}, "event envelope")
            require(bool(item["reason"]), "event.reason", "Нужна причина", 2)
            name, payload, a.reason = item["event"], item["payload"], item["reason"]
            record(state, name, copy.deepcopy(payload), root, task, config)
        state["revision"] += 1
        state["updated_at"] = timestamp()
        state["history"].append(
            {
                "at": state["updated_at"],
                "event": name,
                "from": before["state"],
                "to": state["state"],
                "reason": a.reason,
                "payload": payload,
                "reconciliation": changes,
            }
        )
        validate(state, root, task, config)
        atomic(path, state)
    return {
        "task": a.task,
        "revision": state["revision"],
        "state": state["state"],
        "changes": changes,
    }


if __name__ == "__main__":
    raise SystemExit(run(main))
