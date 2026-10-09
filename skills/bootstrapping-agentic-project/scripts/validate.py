"""Проверка самодостаточности package и структуры установленного harness."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.dont_write_bytecode = True

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "assets/root/scripts/ai"))
common = importlib.import_module("_common")
inside, parser, root_path, run = common.inside, common.parser, common.root_path, common.run
schema = importlib.import_module("schema")
policy, require = schema.policy, schema.require


def main() -> dict:
    """Проверяет canonical files и обнаруживает drift, не перезаписывая instances."""
    p = parser(__doc__)
    a = p.parse_args()
    root = root_path(a.root)
    importlib.import_module("package_checks").check_package(PACKAGE, require)
    policy(root)
    required = [
        ".ai/README.md",
        ".ai/project.md",
        ".ai/architecture/overview.md",
        ".ai/skills.md",
        ".ai/workflow.yaml",
        "AGENTS.md",
    ]
    required += [
        "scripts/ai/" + n
        for n in (
            "bootstrap_task.py",
            "state.py",
            "validate.py",
            "check_stall.py",
            "_common.py",
            "schema.py",
        )
    ]
    for name in required:
        require(inside(root, name).is_file(), "package.missing", "Отсутствует " + name)
    require(
        not (PACKAGE / "assets/root/.agents/skills/bootstrapping-agentic-project").exists(),
        "package.recursion",
        "Recursive package copy",
    )
    drift = []
    for source in (PACKAGE / "assets/root/scripts/ai").glob("*.py"):
        if source.read_bytes() != (root / "scripts/ai" / source.name).read_bytes():
            drift.append("scripts/ai/" + source.name)
    for name in (
        "classifying-development-task",
        "reviewing-implementation",
        "updating-project-knowledge",
        "bootstrapping-agentic-project",
    ):
        path = inside(root, ".agents/skills/" + name + "/SKILL.md")
        require(path.is_file(), "skill.missing", name)
        text = path.read_text()
        require(
            text.startswith("---\n")
            and "\nname: " + name + "\n" in text
            and "\ndescription:" in text,
            "skill.frontmatter",
            "Невалидный skill frontmatter " + name,
        )
    return {
        "ok": not drift,
        "code": 1 if drift else 0,
        "drift": drift,
        "diagnostics": [
            {
                "rule": "package.drift",
                "path": name,
                "message": "Canonical helper отличается от project instance",
                "suggested_action": "Проверить diff; ручной экземпляр не перезаписывать",
            }
            for name in drift
        ],
    }


if __name__ == "__main__":
    raise SystemExit(run(main))
