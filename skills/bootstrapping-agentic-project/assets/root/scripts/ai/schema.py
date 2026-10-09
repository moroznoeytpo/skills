"""Схема v1, фазовые guards и проверка актуальности task gates."""

from __future__ import annotations

from pathlib import Path

from _common import (
    HarnessError,
    date,
    evidence,
    evidence_hashes,
    file_hash,
    fingerprint,
    inside,
    load,
    requirements,
)

LEVELS = {"trivial", "bounded", "planned", "architectural"}
STATES = {
    "created",
    "specifying",
    "waiting_spec_approval",
    "planning",
    "waiting_plan_approval",
    "ready",
    "implementing",
    "verifying",
    "reviewing",
    "updating_knowledge",
    "waiting",
    "blocked",
    "waiting_human",
    "done",
    "failed",
}
WORKING = STATES - {
    "waiting",
    "blocked",
    "waiting_human",
    "waiting_spec_approval",
    "waiting_plan_approval",
    "done",
    "failed",
}
VERIFICATION = {"pending", "running", "passed", "failed", "blocked", "stale"}
REVIEW = {"pending", "running", "passed", "changes_requested", "blocked", "stale", "not_required"}
IMPACT = {"project", "architecture", "adr", "lessons", "agent_rules"}
TRANSITIONS = {
    "created": {"ready", "specifying"},
    "specifying": {"waiting_spec_approval"},
    "waiting_spec_approval": {"specifying", "ready", "planning"},
    "planning": {"waiting_plan_approval"},
    "waiting_plan_approval": {"planning", "ready"},
    "ready": {"implementing"},
    "implementing": {"verifying"},
    "verifying": {"implementing", "reviewing", "updating_knowledge"},
    "reviewing": {"implementing", "updating_knowledge", "waiting_human", "done"},
    "updating_knowledge": {"reviewing", "done"},
    "waiting_human": {"done"},
}


def require(condition: bool, rule: str, message: str, code: int = 1) -> None:
    """Отклоняет нарушение контракта с постоянным rule ID."""
    if not condition:
        raise HarnessError(rule, message, code)


def enum(value: object, allowed: set, path: str) -> None:
    """Проверяет string enum без неявного приведения bool/int."""
    require(isinstance(value, str) and value in allowed, "schema.enum", path, 2)


def fields(value: object, names: set[str], path: str) -> None:
    """Проверяет обязательные поля mapping до обращения к ним."""
    require(isinstance(value, dict) and names <= value.keys(), "schema.fields", path, 2)


def policy(root: Path) -> dict:
    """Читает совместимую политику и конечные лимиты ожиданий."""
    p = load(inside(root, ".ai/workflow.yaml"))
    fields(
        p,
        {
            "harness_version",
            "schema_version",
            "timeouts",
            "stall_policy",
            "ci",
            "production_paths",
            "exclude_paths",
            "knowledge_paths",
        },
        "workflow",
    )
    require(
        type(p["harness_version"]) is int
        and p["harness_version"] == 1
        and type(p["schema_version"]) is int
        and p["schema_version"] == 1,
        "schema.version",
        "Поддерживается только harness/schema v1",
        2,
    )
    fields(p["ci"], {"mode"}, "ci")
    enum(p["ci"].get("mode"), {"warn", "enforce"}, "ci.mode")
    for key in ("short", "normal", "long", "external"):
        fields(p["timeouts"].get(key), {"check_every_seconds", "deadline_seconds"}, key)
        for v in p["timeouts"][key].values():
            require(type(v) is int and v > 0, "policy.timeout", "Нужны положительные секунды", 2)
    for key in ("max_auto_retries", "max_auto_extensions", "extension_factor"):
        v = p["stall_policy"].get(key)
        require(
            type(v) is int and v >= (1 if key == "extension_factor" else 0),
            "policy.limit",
            "Нужны конечные неотрицательные лимиты",
            2,
        )
    for name in ("production_paths", "exclude_paths", "knowledge_paths"):
        require(isinstance(p[name], list), "policy.paths", name, 2)
        for value in p[name]:
            inside(root, value)
    return p


def steps_valid(state: dict) -> None:
    """Проверяет IDs, DAG, dependency completion и единственный running шаг."""
    require(isinstance(state["steps"], list), "schema.steps", "steps должен быть списком", 2)
    indexed = {}
    for s in state["steps"]:
        fields(s, {"id", "title", "depends_on", "status", "verification", "evidence"}, "step")
        require(
            type(s["id"]) is int and s["id"] > 0 and s["id"] not in indexed,
            "step.id",
            "ID должен быть уникальным положительным integer",
            2,
        )
        indexed[s["id"]] = s
        enum(
            s["status"],
            {"pending", "running", "waiting", "blocked", "done", "skipped", "failed"},
            "step.status",
        )
        enum(s["verification"], VERIFICATION, "step.verification")
        require(isinstance(s["depends_on"], list), "step.dependencies", "Нужен список ID", 2)
    visiting, visited = set(), set()

    def visit(key: int) -> None:
        """Обходит dependency DAG и выявляет цикл либо неизвестный ID."""
        require(key in indexed, "step.missing_dependency", "Dependency ID не найден")
        require(key not in visiting, "step.cycle", "Цикл зависимостей")
        if key in visited:
            return
        visiting.add(key)
        for dep in indexed[key]["depends_on"]:
            require(type(dep) is int, "step.dependency_id", "Dependency должен быть integer", 2)
            visit(dep)
        visiting.remove(key)
        visited.add(key)

    for key in indexed:
        visit(key)
    require(
        sum(s["status"] == "running" for s in indexed.values()) <= 1,
        "step.parallel",
        "Последовательный executor допускает один running шаг",
    )
    for s in indexed.values():
        if s["status"] in ("running", "done"):
            require(
                all(indexed[d]["status"] in ("done", "skipped") for d in s["depends_on"]),
                "step.dependencies",
                "Зависимости шага не завершены",
            )
        if s["status"] == "done":
            require(
                s["verification"] == "passed" and bool(s["evidence"]),
                "step.verification",
                "Done требует успешную проверку и evidence",
            )
        if s["status"] == "skipped":
            fields(s.get("exception"), {"reason", "source"}, "step.exception")
            require(
                bool(s["exception"]["reason"]) and bool(s["exception"]["source"]),
                "step.skipped",
                "Исключение требует реального human решения",
            )
    require(
        state["current_step"] is None or state["current_step"] in indexed,
        "step.current",
        "current_step не найден",
        2,
    )


def wait_valid(wait: dict, p: dict) -> None:
    """Проверяет абсолютные сроки и пределы attempts/extensions."""
    fields(
        wait,
        {
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
        "wait",
    )
    enum(wait["kind"], {"process", "agent", "external"}, "wait.kind")
    enum(wait["timeout_class"], set(p["timeouts"]), "wait.timeout_class")
    enum(wait["resume_state"], WORKING, "wait.resume_state")
    require(
        bool(wait["condition"]) and bool(wait["probe"]), "wait.observation", "Нужны condition/probe"
    )
    start, check, deadline = (date(wait[k]) for k in ("started_at", "check_after", "deadline"))
    require(start <= check <= deadline, "wait.time", "Неверный порядок сроков")
    for key, limit in (
        ("attempts", 1 + p["stall_policy"]["max_auto_retries"]),
        ("extensions", p["stall_policy"]["max_auto_extensions"]),
    ):
        require(
            type(wait[key]) is int and (1 if key == "attempts" else 0) <= wait[key] <= limit,
            "wait.limit",
            "Превышен автоматический лимит или неверный счётчик",
        )


def validate(state: dict, root: Path, task: Path, p: dict, *, historical: bool = False) -> None:
    """Проверяет структурные и фазовые инварианты, не изменяя документ."""
    for artifact in ("state.yaml", "spec.md", "plan.md", "implementation.md", "review.md"):
        inside(task, artifact)
    names = {
        "version",
        "revision",
        "task",
        "title",
        "external_id",
        "level",
        "classification",
        "state",
        "current_step",
        "resume_state",
        "created_at",
        "updated_at",
        "scope",
        "scope_paths",
        "next_action",
        "repository",
        "steps",
        "approvals",
        "verification",
        "review",
        "knowledge_update",
        "progress",
        "wait",
        "blocker",
        "history",
    }
    fields(state, names, "state")
    require(
        type(state["version"]) is int and state["version"] == 1,
        "schema.version",
        "Поддерживается state version 1",
        2,
    )
    require(
        type(state["revision"]) is int and state["revision"] > 0,
        "schema.revision",
        "revision > 0",
        2,
    )
    require(state["task"] == task.name, "task.identity", "task не совпадает с каталогом", 2)
    enum(state["level"], LEVELS, "level")
    enum(state["state"], STATES, "state")
    if state["resume_state"] is not None:
        enum(state["resume_state"], WORKING, "resume_state")
    for key in ("created_at", "updated_at"):
        date(state[key])
    fields(state["classification"], {"reason", "signals", "history"}, "classification")
    require(bool(state["classification"]["reason"]), "classification.reason", "Нужно основание")
    require(
        isinstance(state["classification"]["signals"], dict)
        and all(type(v) is bool for v in state["classification"]["signals"].values()),
        "classification.signals",
        "Признаки должны быть boolean",
        2,
    )
    fields(state["repository"], {"base_commit", "checkout"}, "repository")
    require(isinstance(state["scope_paths"], list), "scope.paths", "Нужен список scope", 2)
    for path in state["scope_paths"]:
        inside(root, path)
    require(isinstance(state["history"], list), "schema.history", "Нужна история", 2)
    fields(state["progress"], {"last_progress_at", "last_action", "last_observed_at"}, "progress")
    for key in ("last_progress_at", "last_observed_at"):
        date(state["progress"][key])
    steps_valid(state)
    for s in state["steps"]:
        if s["status"] == "done":
            evidence(task, s["evidence"])
            require(
                s.get("evidence_hashes") == evidence_hashes(task, s["evidence"]),
                "step.evidence_stale",
                "Evidence шага изменено или не зарегистрировано; выполните resume",
            )
    fields(state["approvals"], {"spec", "plan", "final"}, "approvals")
    for key, a in state["approvals"].items():
        fields(a, {"status"}, "approval")
        enum(
            a["status"],
            {"pending", "approved", "rejected", "stale", "not_required"},
            "approval.status",
        )
        if a["status"] == "approved":
            fields(a, {"source", "scope_summary", "scope_fingerprint", "decided_at"}, "approval")
            require(
                bool(a["source"]) and bool(a["scope_summary"]),
                "approval.source",
                "Нужен human source/scope",
            )
            date(a["decided_at"])
        if a["status"] == "not_required":
            require(bool(a.get("reason")), "approval.reason", "Нужно основание not_required")
    fields(
        state["verification"],
        {"status", "evidence", "scope_fingerprint", "limitations"},
        "verification",
    )
    enum(state["verification"]["status"], VERIFICATION, "verification.status")
    fields(state["review"], {"status", "mode", "evidence"}, "review")
    enum(state["review"]["status"], REVIEW, "review.status")
    if state["review"]["status"] == "not_required":
        require(
            state["level"] == "trivial"
            and state["review"]["mode"] is None
            and bool(state["review"].get("reason")),
            "review.required",
            "Review обязательно для этого уровня",
        )
    else:
        enum(state["review"]["mode"], {"code", "final"}, "review.mode")
    k = state["knowledge_update"]
    fields(k, {"status", "impact", "rationale", "changes", "notification"}, "knowledge_update")
    enum(
        k["status"],
        {"pending", "running", "updated", "no_change", "blocked", "stale"},
        "knowledge.status",
    )
    fields(k["impact"], IMPACT, "knowledge.impact")
    for answer in k["impact"].values():
        enum(answer, {"unknown", "yes", "no"}, "knowledge.answer")
    if k["status"] in ("updated", "no_change"):
        require(
            all(a != "unknown" for a in k["impact"].values())
            and all(k["rationale"].get(key) for key in IMPACT),
            "knowledge.incomplete",
            "Ответьте на пять вопросов",
        )
        require(bool(k["notification"]), "knowledge.notification", "Нужно фактическое уведомление")
        if k["status"] == "no_change":
            require(
                set(k["impact"].values()) == {"no"} and not k["changes"],
                "knowledge.no_change",
                "no_change допускает только пять no",
            )
        if "yes" in k["impact"].values():
            require(
                bool(k["changes"]), "knowledge.changes", "Нужны изменения или human disposition"
            )
    if state["wait"] is not None:
        wait_valid(state["wait"], p)
        require(
            state["wait"]["step_id"] in {s["id"] for s in state["steps"]},
            "wait.step",
            "Шаг не найден",
        )
    if state["state"] == "waiting":
        require(state["wait"] is not None, "wait.required", "Нет wait контракта")
    if state["blocker"] is not None:
        fields(
            state["blocker"],
            {
                "step_id",
                "expected",
                "observed",
                "investigation",
                "attempts",
                "likely_cause",
                "next_action",
                "resume_state",
            },
            "blocker",
        )
    if state["state"] == "blocked":
        require(state["blocker"] is not None, "blocker.required", "Нет диагностики blocker")
    if state["state"] == "waiting_human":
        fields(state.get("human_gate"), {"kind", "question", "resume_state"}, "human_gate")
    for name, needed in (
        ("spec", state["level"] != "trivial"),
        ("plan", state["level"] in ("planned", "architectural")),
    ):
        if needed and state["state"] not in (
            "created",
            "specifying",
            "waiting_spec_approval",
            "planning",
        ):
            require((inside(task, name + ".md")).is_file(), "artifact.missing", name)
    if state["level"] != "trivial" and state["state"] in (
        "reviewing",
        "updating_knowledge",
        "done",
    ):
        document_ready(task, "implementation")
    if state["state"] == "done":
        done(state, root, task, p, historical=historical)


def step_current(
    s: dict, state: dict, root: Path, task: Path, p: dict, visited: set | None = None
) -> None:
    """Проверяет содержимое prerequisite перед зависимым запуском и при аудите."""
    visited = set() if visited is None else visited
    if s["id"] in visited:
        return
    visited.add(s["id"])
    for ancestor in state["steps"]:
        if ancestor["id"] in s["depends_on"]:
            step_current(ancestor, state, root, task, p, visited)
    if s["status"] == "done":
        require(
            s.get("evidence_hashes") == evidence_hashes(task, s["evidence"]),
            "step.evidence_stale",
            "Evidence prerequisite изменено",
        )
        require(
            s.get("scope_fingerprint")
            == fingerprint(
                root,
                {**state, "scope_paths": s.get("scope_paths", state["scope_paths"])},
                {**p, "knowledge_paths": []},
            ),
            "step.stale",
            "Файлы prerequisite изменены; выполните resume и перепроверку",
        )


def approved(state: dict, task: Path, name: str) -> None:
    """Проверяет approval именно существующего содержимого spec/plan."""
    a = state["approvals"][name]
    require(
        a["status"] == "approved"
        and a.get("scope_fingerprint") == file_hash(inside(task, name + ".md")),
        "approval.stale",
        "Требуется согласование текущей " + name,
    )


def ready(state: dict, task: Path) -> None:
    """Открывает исполнение только конкретного одобренного scope."""
    require(
        bool(state["scope"]) and bool(state["scope_paths"]) and bool(state["steps"]),
        "scope.empty",
        "Перед ready нужны цель, конкретные пути и шаги",
    )
    if state["level"] != "trivial":
        approved(state, task, "spec")
    if state["level"] in ("planned", "architectural"):
        approved(state, task, "plan")


def result_current(
    result: dict,
    state: dict,
    root: Path,
    task: Path,
    p: dict,
    *,
    final: bool = False,
    historical: bool = False,
) -> None:
    """Связывает passed gate с текущими файлами, требованиями и evidence."""
    require(result["status"] == "passed", "gate.not_passed", "Обязательная проверка не passed")
    require(
        result.get("evidence_hashes") == evidence_hashes(task, result["evidence"]),
        "evidence.stale",
        "Evidence изменено после проверки",
    )
    if result.get("review_artifact_hash") is not None:
        require(
            (inside(task, "review.md")).is_file()
            and result["review_artifact_hash"] == file_hash(inside(task, "review.md")),
            "review.artifact_stale",
            "Обязательный review.md изменён или утрачен",
        )
    require(
        (historical or result.get("scope_fingerprint") == fingerprint(root, state, p, final=final))
        and result.get("requirements_fingerprints") == requirements(task, state["level"]),
        "gate.stale",
        "Evidence относится к прежнему scope/spec/plan",
    )


def review_valid(review: dict) -> None:
    """Проверяет независимого reviewer и допустимую диспозицию findings."""
    require(
        review.get("independent") is True and bool(review.get("reviewer")),
        "review.independence",
        "Нужно независимое review с identity",
    )
    require(isinstance(review.get("findings"), list), "review.findings", "Нужен список findings", 2)
    for f in review["findings"]:
        fields(
            f,
            {"id", "severity", "location", "description", "evidence", "expected_fix", "status"},
            "finding",
        )
        enum(f["severity"], {"critical", "major", "minor", "suggestion"}, "finding.severity")
        enum(f["status"], {"open", "fixed", "accepted_risk", "not_a_defect"}, "finding.status")
        if f["severity"] != "suggestion":
            require(f["status"] != "open", "review.open_finding", "Открытый обязательный finding")
        if f["status"] != "open":
            require(bool(f.get("resolution")), "review.resolution", "Нужно основание disposition")
        if f["severity"] in ("critical", "major") and f["status"] == "accepted_risk":
            require(bool(f.get("human_source")), "review.risk", "Принятие риска требует человека")


def done(state: dict, root: Path, task: Path, p: dict, *, historical: bool = False) -> None:
    """Закрывает задачу только при выполнении всех актуальных terminal guards."""
    ready(state, task)
    if state["level"] != "trivial":
        document_ready(task, "implementation")
    require(
        all(s["status"] in ("done", "skipped") for s in state["steps"]),
        "done.steps",
        "Шаги не завершены",
    )
    result_current(state["verification"], state, root, task, p, historical=historical)
    require(
        not state["verification"].get("required_unmet"),
        "done.external",
        "Обязательные проверки не выполнены",
    )
    review = state["review"]
    if review["status"] != "not_required":
        require(review["mode"] == "final", "done.final_review", "Нужно final review кода и знаний")
        require(
            bool(review.get("review_artifact_hash")), "review.artifact", "Нет fingerprint review.md"
        )
        result_current(review, state, root, task, p, final=True, historical=historical)
        review_valid(review)
    require(
        state["knowledge_update"]["status"] in ("updated", "no_change"),
        "done.knowledge",
        "Knowledge check не завершён",
    )
    require(
        state["wait"] is None and state["blocker"] is None, "done.blocked", "Открыты wait/blocker"
    )
    if state["level"] in ("planned", "architectural") or state.get("final_human_required"):
        a = state["approvals"]["final"]
        require(
            a["status"] == "approved"
            and (
                historical or a.get("scope_fingerprint") == fingerprint(root, state, p, final=True)
            ),
            "done.human",
            "Нужна human acceptance текущего результата",
        )
    require(bool(state["next_action"]), "done.next_action", "Нужен итоговый next_action")


def document_ready(task: Path, name: str) -> None:
    """Не допускает пустую заготовку до запроса approval."""
    p = inside(task, name + ".md")
    require(
        p.is_file() and len(p.read_text().strip()) > 20 and "HARNESS_DRAFT" not in p.read_text(),
        "artifact.draft",
        "Подготовьте содержательный " + name,
    )
