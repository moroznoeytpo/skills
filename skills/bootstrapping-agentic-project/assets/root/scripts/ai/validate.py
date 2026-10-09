"""Read-only проверка harness, gates, ссылок и покрытия Git diff."""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from urllib.parse import unquote

sys.dont_write_bytecode = True

common_module = importlib.import_module("_common")
HarnessError = common_module.HarnessError
fingerprint = common_module.fingerprint
git = common_module.git
inside = common_module.inside
load = common_module.load
matches = common_module.matches
parser = common_module.parser
root_path = common_module.root_path
run = common_module.run
task_path = common_module.task_path
schema_module = importlib.import_module("schema")
approved = schema_module.approved
done = schema_module.done
policy = schema_module.policy
ready = schema_module.ready
step_current = schema_module.step_current
require = schema_module.require
result_current = schema_module.result_current
validate = schema_module.validate


def changed_paths(root: Path, base: str) -> set[str]:
    """Включает dirty/untracked, оба имени rename и удаления от merge base."""
    merge = git(root, "merge-base", base, "HEAD")
    raw = git(root, "diff", "--name-status", "-z", "--find-renames", merge, "--").split("\0")
    result = set()
    index = 0
    while index < len(raw) and raw[index]:
        status = raw[index]
        index += 1
        for _ in range(2 if status.startswith(("R", "C")) else 1):
            result.add(raw[index])
            index += 1
    result.update(
        filter(None, git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0"))
    )
    return result


def links(root: Path, files: list[Path]) -> None:
    """Проверяет локальные Markdown цели, не переходя по внешним URL."""
    for f in files:
        for raw in re.findall(r"\]\(([^)]+)\)", f.read_text(encoding="utf-8")):
            raw = raw.strip("<>").split(" ")[0]
            if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", raw) or raw.startswith("#"):
                continue
            relative = unquote(raw.split("#")[0])
            if not relative:
                continue
            target = (f.parent / relative).resolve()
            require(
                target.is_relative_to(root),
                "link.escape",
                "Локальная ссылка выходит за root: " + str(f),
            )
            require(target.exists(), "link.missing", "Битая ссылка " + relative + " в " + str(f))


def adr_links(root: Path) -> None:
    """Проверяет уникальность ADR IDs и двустороннее supersede metadata."""
    records = {}
    for path in (root / ".ai/decisions").glob("ADR-*.md"):
        match = re.match(r"ADR-(\d+)-", path.name)
        require(
            match is not None and match[1] not in records, "adr.id", "ADR ID невалиден/повторён"
        )
        records[match[1]] = path
        content = path.read_text()
        if "status: accepted" in content:
            require(
                "approval_source:" in content
                and bool(re.search(r"^approval_source:[ \t]*[^\s]+", content, re.M)),
                "adr.approval",
                "Accepted ADR требует human source",
            )
    for key, path in records.items():
        text = path.read_text()
        for field, reciprocal in (("supersedes", "superseded_by"), ("superseded_by", "supersedes")):
            match = re.search(r"^" + field + r":\s*ADR-(\d+)", text, re.M)
            if match:
                require(match[1] in records, "adr.link", "Отсутствующий ADR")
                require(
                    re.search(
                        r"^" + reciprocal + r":\s*ADR-" + key + r"\b",
                        records[match[1]].read_text(),
                        re.M,
                    )
                    is not None,
                    "adr.reciprocal",
                    "Нет обратной supersede ссылки",
                )


def inspect(root: Path, task: Path, p: dict, *, historical: bool = False) -> dict:
    """Проверяет state и свежесть gates даже до попытки DONE."""
    state = load(inside(task, "state.yaml"))
    historical = historical and state["state"] == "done"
    validate(state, root, task, p, historical=historical)
    if not historical:
        for s in state["steps"]:
            step_current(s, state, root, task, p)
    for name in ("spec", "plan"):
        if state["approvals"][name]["status"] == "approved":
            approved(state, task, name)
    if state["state"] in (
        "ready",
        "implementing",
        "verifying",
        "reviewing",
        "updating_knowledge",
        "done",
    ):
        ready(state, task)
    for name in ("verification", "review"):
        if state[name]["status"] == "passed":
            result_current(
                state[name],
                state,
                root,
                task,
                p,
                final=name == "review" and state[name]["mode"] == "final",
                historical=historical,
            )
    if not historical and state["approvals"]["final"]["status"] == "approved":
        require(
            state["approvals"]["final"]["scope_fingerprint"]
            == fingerprint(root, state, p, final=True),
            "approval.final_stale",
            "Final approval stale",
        )
    return state


def main() -> dict:
    """Возвращает все найденные diagnostics; warn снижает только policy errors."""
    p = parser(__doc__)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--task")
    group.add_argument("--all", action="store_true")
    p.add_argument("--base")
    p.add_argument("--mode", choices=["warn", "enforce"])
    a = p.parse_args()
    root = root_path(a.root)
    config = policy(root)
    mode = a.mode or config["ci"]["mode"]
    tasks = [task_path(root, a.task)] if a.task else sorted(inside(root, ".ai/tasks").glob("*/"))
    diagnostics, codes, states = [], [], []

    def capture(action) -> None:
        """Собирает независимые нарушения без подавления parse/I/O errors."""
        try:
            action()
        except HarnessError as error:
            diagnostics.append(error.diagnostic)
            codes.append(error.code)

    for task in tasks:
        capture(
            lambda task=task: states.append(
                inspect(root, task_path(root, task.name), config, historical=not bool(a.task))
            )
        )
    capture(lambda: adr_links(root))
    files = []
    if not a.task:
        for directory in (".ai", ".ai/architecture", ".ai/decisions", ".ai/lessons"):
            files.extend((root / directory).glob("*.md"))
    for task in tasks:
        files.extend(
            f
            for f in task.glob("*.md")
            if f.name in {"spec.md", "plan.md", "implementation.md", "review.md"}
        )
    capture(lambda: links(root, files))
    if a.base:

        def check_diff() -> None:
            """Проверяет текущую поставку без требования закрыть посторонние задачи."""
            changed = changed_paths(root, a.base)
            bad = sorted(
                p
                for p in changed
                if matches(p, ["docs/superpowers/specs", "docs/superpowers/plans"])
            )
            require(
                not bad,
                "paths.superpowers",
                "Task spec/plan должны находиться в .ai/tasks: " + ", ".join(bad),
            )
            production = {
                p
                for p in changed
                if matches(p, config["production_paths"])
                and not matches(p, config["exclude_paths"])
            }
            covered = set()
            for state in states:
                if state["state"] == "done" and state["repository"]["base_commit"]:
                    task = task_path(root, state["task"])
                    try:
                        done(state, root, task, config)
                    except HarnessError:
                        continue
                    actual = changed_paths(root, state["repository"]["base_commit"])
                    covered.update(
                        p for p in production & actual if matches(p, state["scope_paths"])
                    )
            require(
                production <= covered,
                "ci.uncovered",
                "Production diff без завершённой актуальной задачи: "
                + ", ".join(sorted(production - covered)),
            )

        capture(check_diff)
    code = 3 if 3 in codes else 2 if 2 in codes else 1 if codes and mode == "enforce" else 0
    return {
        "ok": code == 0,
        "code": code,
        "mode": mode,
        "diagnostics": diagnostics,
        "tasks_checked": len(tasks),
        "policy_warnings": len(codes) if mode == "warn" else 0,
    }


if __name__ == "__main__":
    raise SystemExit(run(main))
