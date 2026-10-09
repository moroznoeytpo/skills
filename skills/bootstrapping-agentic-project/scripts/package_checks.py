"""Проверка обязательного состава переносимого пакета до установки."""

from pathlib import Path


def check_package(package: Path, require) -> None:
    """Отклоняет неполные references, шаблоны и executable payload до записи."""
    names = [
        "SKILL.md",
        "assets/agents-block.md",
        "assets/templates/state.yaml",
        "assets/templates/adr.md",
        "scripts/install.py",
        "scripts/validate.py",
        "scripts/package_checks.py",
    ]
    names += [
        "references/" + name + ".md"
        for name in (
            "bootstrap-process",
            "task-classification",
            "knowledge-lifecycle",
            "install-update-policy",
            "ci-integration",
            "workflow-states",
            "event-schema",
        )
    ]
    names += [
        "assets/root/scripts/ai/" + name + ".py"
        for name in ("_common", "schema", "bootstrap_task", "state", "validate", "check_stall")
    ]
    names += [
        "assets/root/.agents/skills/" + name + "/SKILL.md"
        for name in (
            "classifying-development-task",
            "reviewing-implementation",
            "updating-project-knowledge",
        )
    ]
    names += [
        "assets/root/" + name
        for name in (
            "requirements-ai.in",
            "requirements-ai.lock",
            ".ai/README.md",
            ".ai/project.md",
            ".ai/workflow.yaml",
            ".ai/skills.md",
            ".ai/architecture/overview.md",
            ".ai/decisions/README.md",
            ".ai/lessons/lessons.md",
        )
    ]
    for name in names:
        path = package / name
        require(
            path.is_file() and path.stat().st_size > 0,
            "package.incomplete",
            "Отсутствует обязательный ресурс " + name,
        )
        require(
            path.resolve().is_relative_to(package.resolve()),
            "package.escape",
            "Ресурс находится вне пакета: " + name,
        )
