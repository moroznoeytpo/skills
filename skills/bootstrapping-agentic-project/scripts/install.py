"""Детерминированный install/update/audit без перезаписи ручных экземпляров."""

from __future__ import annotations

import difflib
import importlib
import sys
from pathlib import Path

sys.dont_write_bytecode = True

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "assets/root/scripts/ai"))
common = importlib.import_module("_common")
inside, load, parser, root_path, run = (
    common.inside,
    common.load,
    common.parser,
    common.root_path,
    common.run,
)
require = importlib.import_module("schema").require

START = "<!-- agentic-harness:start -->"
END = "<!-- agentic-harness:end -->"


def proposals(root: Path) -> tuple[list, list, list]:
    """Сравнивает canonical payload и package с экземплярами, сохраняя conflicts."""
    additions, conflicts, unchanged = [], [], []
    targets = {}
    for path in (PACKAGE / "assets/root").rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            targets[path.relative_to(PACKAGE / "assets/root").as_posix()] = path.read_bytes()
    target_package = root / ".agents/skills/bootstrapping-agentic-project"
    if target_package.resolve() != PACKAGE:
        for path in PACKAGE.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                targets[
                    ".agents/skills/bootstrapping-agentic-project/"
                    + path.relative_to(PACKAGE).as_posix()
                ] = path.read_bytes()
    for name, content in targets.items():
        target = inside(root, name)
        if not target.exists():
            additions.append((name, content))
        elif target.is_file() and target.read_bytes() == content:
            unchanged.append(name)
        else:
            old = target.read_text(encoding="utf-8") if target.is_file() else "<directory>"
            patch = "".join(
                difflib.unified_diff(
                    old.splitlines(True),
                    content.decode().splitlines(True),
                    fromfile=name,
                    tofile=name,
                )
            )
            conflicts.append(
                {
                    "path": name,
                    "diff": patch,
                    "action": "Ручной экземпляр сохранён; применить адресный patch после review",
                }
            )
    route = (PACKAGE / "assets/agents-block.md").read_text()
    agent = inside(root, "AGENTS.md")
    original = agent.read_bytes() if agent.is_file() else b""
    text = original.decode("utf-8")
    if START not in text and END not in text:
        additions.append(("AGENTS.md", original + (b"\n\n" if original else b"") + route.encode()))
    elif text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        conflicts.append(
            {
                "path": "AGENTS.md",
                "diff": "Malformed/duplicate managed markers",
                "action": "Сохранить и исправить адресно",
            }
        )
    else:
        block = text[text.index(START) : text.index(END) + len(END)]
        if block.strip() != route.strip():
            conflicts.append(
                {
                    "path": "AGENTS.md",
                    "diff": "".join(
                        difflib.unified_diff(block.splitlines(True), route.splitlines(True))
                    ),
                    "action": "Сохранён ручной текст внутри markers",
                }
            )
        else:
            unchanged.append("AGENTS.md")
    return additions, conflicts, unchanged


def main() -> dict:
    """Пишет только безопасные additions после полного preflight всех путей."""
    p = parser(__doc__)
    p.add_argument("--mode", choices=["install", "update", "audit"], required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    root = root_path(a.root)
    importlib.import_module("package_checks").check_package(PACKAGE, require)
    workflow = inside(root, ".ai/workflow.yaml")
    if workflow.exists():
        version = load(workflow)
        require(
            version.get("harness_version") == 1 and version.get("schema_version") == 1,
            "schema.version",
            "Неизвестная версия; запись запрещена",
            2,
        )
    require(
        not (root / "AGENTS.override.md").exists(),
        "install.override",
        "Активный override требует согласованного routing patch; автоматическая запись не выполняется",
    )
    tasks = inside(root, ".ai/tasks")
    require(
        not tasks.exists() or tasks.is_dir(), "install.tasks", "Task root должен быть каталогом"
    )
    additions, conflicts, unchanged = proposals(root)
    originals = {
        name: inside(root, name).read_bytes() if inside(root, name).is_file() else None
        for name, _ in additions
    }
    wrote = []
    if not a.dry_run and a.mode != "audit":
        for name, content in additions:
            target = inside(root, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            require(
                (target.read_bytes() if target.is_file() else None) == originals[name],
                "install.concurrent",
                "Файл изменён конкурентно; повторите audit",
            )
            target.write_bytes(content)
            wrote.append(name)
        tasks.mkdir(exist_ok=True)
    code = 1 if conflicts else 0
    return {
        "ok": code == 0,
        "code": code,
        "mode": a.mode,
        "dry_run": a.dry_run,
        "existing_harness": workflow.exists(),
        "missing": [n for n, _ in additions],
        "conflicts": conflicts,
        "unchanged": unchanged,
        "written": wrote,
        "diagnostics": [
            {
                "rule": "install.conflict",
                "path": c["path"],
                "message": "Ручной экземпляр сохранён",
                "suggested_action": c["action"],
            }
            for c in conflicts
        ],
    }


if __name__ == "__main__":
    raise SystemExit(run(main))
