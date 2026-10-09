"""Перенос package, dry-run и preservation ручных project instances."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from conftest import ROOT

PACKAGE = ROOT / "skills/bootstrapping-agentic-project"


def tree(root: Path) -> dict:
    """Снимает hashes всех файлов fixture для контроля отсутствия записи."""
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }


def install(root: Path, mode: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Вызывает действительный переносимый installer без глобальной установки."""
    return subprocess.run(
        [
            sys.executable,
            "-B",
            str(PACKAGE / "scripts/install.py"),
            "--root",
            str(root),
            "--mode",
            mode,
            "--json",
            *args,
        ],
        capture_output=True,
        text=True,
    )


def test_install_audit_dryrun_and_idempotent(tmp_path: Path) -> None:
    """Audit/dry-run не пишут, повторный install не дублирует block или skills."""
    root = tmp_path / "static-site"
    root.mkdir()
    (root / "index.html").write_text("<h1>Other project</h1>")
    (root / "AGENTS.md").write_text("KEEP-MANUAL-RULE\n")
    before = tree(root)
    for mode in ("audit", "install", "update"):
        result = install(root, mode, "--dry-run")
        assert result.returncode in (0, 1), result.stderr
        assert tree(root) == before
    result = install(root, "install")
    assert result.returncode == 0, result.stdout + result.stderr
    after = tree(root)
    assert "KEEP-MANUAL-RULE" in (root / "AGENTS.md").read_text()
    assert install(root, "install").returncode == 0
    assert tree(root) == after
    assert install(root, "update").returncode == 0
    assert tree(root) == after
    assert not list((root / ".ai/tasks").glob("*/state.yaml"))


def test_update_preserves_manual_marker_and_policy(tmp_path: Path) -> None:
    """Конфликт показывает diff и сохраняет авторский текст даже внутри markers."""
    root = tmp_path / "site"
    root.mkdir()
    assert install(root, "install").returncode == 0
    path = root / "AGENTS.md"
    path.write_text(
        path.read_text().replace(
            "<!-- agentic-harness:end -->", "KEEP-INSIDE\n<!-- agentic-harness:end -->"
        )
    )
    policy = root / ".ai/workflow.yaml"
    policy.write_text(policy.read_text().replace("deadline_seconds: 300", "deadline_seconds: 333"))
    architecture = root / ".ai/architecture/overview.md"
    architecture.write_text(architecture.read_text() + "\nKEEP-ARCHITECTURE\n")
    skill = root / ".agents/skills/reviewing-implementation/SKILL.md"
    skill.write_text(skill.read_text() + "\nKEEP-PROJECT-SKILL\n")
    before = tree(root)
    result = install(root, "update")
    assert result.returncode == 1, result.stdout
    data = json.loads(result.stdout)
    assert data["conflicts"]
    assert tree(root) == before
    assert "KEEP-INSIDE" in path.read_text()


def test_package_standalone_and_no_source_project_leak(tmp_path: Path) -> None:
    """Копирование только package достаточно для другого типа проекта."""
    import shutil

    copied = tmp_path / "package"
    shutil.copytree(PACKAGE, copied)
    root = tmp_path / "new-root"
    root.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(copied / "scripts/install.py"),
            "--root",
            str(root),
            "--mode",
            "install",
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in (".md", ".yaml", ".py"):
            text = p.read_text()
            assert "/Users/moroznoeytpo" not in text
            assert "ERAMCO" not in text
    assert not (copied / "assets/root/.agents/skills/bootstrapping-agentic-project").exists()


def test_manual_agent_bytes_preserved(tmp_path: Path) -> None:
    """Установка сохраняет исходные пробелы, CRLF и пустые строки побайтно."""
    root = tmp_path / "manual"
    root.mkdir()
    original = b"\n  KEEP-MANUAL-RULE\r\n\r\n"
    (root / "AGENTS.md").write_bytes(original)
    assert install(root, "install").returncode == 0
    assert (root / "AGENTS.md").read_bytes().startswith(original)


def test_tasks_symlink_fails_before_any_write(tmp_path: Path) -> None:
    """Недопустимый task root обнаруживается до создания остальных файлов."""
    root = tmp_path / "target"
    (root / ".ai").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / ".ai/tasks").symlink_to(outside, target_is_directory=True)
    before = tree(root)
    assert install(root, "install").returncode != 0
    assert tree(root) == before
    assert not list(outside.iterdir())


def test_audit_without_python_flag_never_writes(tmp_path: Path) -> None:
    """Обычный Python audit не создаёт bytecode внутри проверяемого проекта."""
    import shutil

    root = tmp_path / "project"
    copied = root / ".agents/skills/bootstrapping-agentic-project"
    shutil.copytree(PACKAGE, copied, ignore=shutil.ignore_patterns("__pycache__"))
    before = tree(root)
    result = subprocess.run(
        [
            sys.executable,
            str(copied / "scripts/install.py"),
            "--root",
            str(root),
            "--mode",
            "audit",
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert tree(root) == before


def test_missing_reference_rejected_before_install(tmp_path: Path) -> None:
    """Неполный переносимый пакет отклоняется до любой записи в целевой root."""
    import shutil

    copied = tmp_path / "incomplete"
    shutil.copytree(PACKAGE, copied)
    (copied / "references/knowledge-lifecycle.md").unlink()
    root = tmp_path / "target"
    root.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(copied / "scripts/install.py"),
            "--root",
            str(root),
            "--mode",
            "install",
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not list(root.iterdir())
