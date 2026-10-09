"""Безопасный ввод, пути, fingerprints и атомарная запись инструментов harness."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

# Read-only CLI не создают bytecode внутри проверяемого checkout.
sys.dont_write_bytecode = True


class HarnessError(Exception):
    """Передаёт стабильный код и адресную диагностику без raw input/traceback."""

    def __init__(self, rule: str, message: str, code: int = 1, path: str = "") -> None:
        """Сохраняет безопасную причину отказа и рекомендуемое действие."""
        super().__init__(message)
        self.code = code
        self.diagnostic = {
            "rule": rule,
            "path": path,
            "message": message,
            "suggested_action": "Исправьте указанную причину и повторите операцию.",
        }


class StrictLoader(yaml.SafeLoader):
    """Загружает безопасные YAML-типы, запрещая неоднозначные mapping keys."""

    def construct_mapping(self, node: Any, deep: bool = False) -> dict:
        """Отклоняет duplicate keys, включая коллизии после implicit resolution."""
        if not isinstance(node, yaml.MappingNode):
            raise HarnessError("yaml.mapping", "Ожидался mapping", 2)
        self.flatten_mapping(node)
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                if key in result:
                    raise HarnessError("yaml.duplicate", "Повторный YAML key", 2)
                result[key] = self.construct_object(value_node, deep=deep)
            except TypeError as error:
                raise HarnessError("yaml.key", "Невалидный mapping key", 2) from error
        return result


def load(path: Path) -> dict:
    """Читает mapping с различением I/O и YAML/format ошибок."""
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=StrictLoader)
    except (OSError, UnicodeError) as error:
        raise HarnessError("io.read", "Не удалось прочитать UTF-8 файл", 3, str(path)) from error
    except yaml.YAMLError as error:
        raise HarnessError("yaml.parse", "Невалидный безопасный YAML", 2, str(path)) from error
    if not isinstance(value, dict):
        raise HarnessError("schema.mapping", "Ожидался объект", 2, str(path))
    return value


def timestamp() -> str:
    """Возвращает однозначное timezone-aware время записи."""
    return dt.datetime.now(dt.timezone.utc).isoformat()


def date(value: Any) -> dt.datetime:
    """Проверяет ISO8601 со смещением без implicit YAML datetime."""
    try:
        result = dt.datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError("timezone")
        return result
    except (ValueError, TypeError) as error:
        raise HarnessError("schema.datetime", "Нужно ISO8601 время с timezone", 2) from error


def inside(root: Path, relative: str, *, allow_root: bool = False) -> Path:
    """Разрешает repo-relative путь без traversal и symlink выхода за root."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise HarnessError("path.invalid", "Нужен относительный POSIX путь", 2)
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or (str(path) == "." and not allow_root):
        raise HarnessError("path.escape", "Путь должен находиться внутри проекта", 1, relative)
    target = root / path
    if not target.resolve().is_relative_to(root.resolve()):
        raise HarnessError("path.symlink", "Symlink выходит за разрешённый root", 1, relative)
    return target


def root_path(value: str) -> Path:
    """Проверяет явно выбранный root и не устанавливает harness в случайный cwd."""
    root = Path(value).resolve()
    if not root.is_dir():
        raise HarnessError("root.missing", "Корень проекта недоступен", 3, str(root))
    return root


def task_path(root: Path, name: str) -> Path:
    """Проверяет canonical task name и containment реального каталога."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise HarnessError("task.name", "Нужно YYYY-MM-DD-lowercase-slug", 2, name)
    try:
        dt.date.fromisoformat(name[:10])
    except ValueError as error:
        raise HarnessError("task.date", "Невалидная дата каталога", 2, name) from error
    return inside(root, ".ai/tasks/" + name)


def git(root: Path, *args: str) -> str:
    """Выполняет только явно заданные Git argv без shell и пользовательского кода."""
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise HarnessError("git.resource", "Git ref/checkout недоступен: " + args[0], 3)
    return result.stdout.strip()


def repository(root: Path) -> dict:
    """Записывает фактическую Git identity либо явное non-Git ограничение."""
    try:
        if Path(git(root, "rev-parse", "--show-toplevel")).resolve() != root:
            raise HarnessError("git.root", "Укажите Git root, а не вложенный каталог", 1)
        return {
            "base_commit": git(root, "rev-parse", "HEAD"),
            "checkout": str(root),
            "branch": git(root, "branch", "--show-current"),
        }
    except HarnessError as error:
        if error.code != 3:
            raise
        return {
            "base_commit": None,
            "checkout": None,
            "limitation": "non-Git: diff/base unavailable",
        }


def file_hash(path: Path) -> str:
    """Считает SHA256 одного существующего артефакта."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise HarnessError("fingerprint.missing", "Артефакт недоступен", 3, str(path)) from error


def matches(path: str, prefixes: list[str]) -> bool:
    """Проверяет файловое/каталожное scope без небезопасного строкового префикса."""
    return any(path == p.rstrip("/") or path.startswith(p.rstrip("/") + "/") for p in prefixes)


def requirements(task: Path, level: str) -> dict:
    """Связывает результаты с текущей spec/plan по матрице уровня."""
    return {
        name: file_hash(inside(task, name + ".md")) if needed else None
        for name, needed in (
            ("spec", level != "trivial"),
            ("plan", level in ("planned", "architectural")),
        )
    }


def fingerprint(root: Path, state: dict, policy: dict, *, final: bool = False) -> str:
    """Учитывает scope contents, новые файлы и удаления без state/review самоссылки."""
    paths = set()
    prefixes = list(state["scope_paths"])
    if final:
        prefixes += policy["knowledge_paths"]
    for prefix in prefixes:
        target = inside(root, prefix)
        if target.is_dir():
            for current, dirs, files in os.walk(target, followlinks=False):
                for name in list(dirs):
                    p = Path(current) / name
                    inside(root, p.relative_to(root).as_posix())
                    if p.is_symlink():
                        raise HarnessError(
                            "path.symlink", "Каталог scope не должен быть symlink", 1
                        )
                for name in files:
                    paths.add((Path(current) / name).relative_to(root).as_posix())
        else:
            paths.add(prefix.rstrip("/"))
    digest = hashlib.sha256()
    for name in sorted(paths):
        if matches(name, [".ai/tasks"]) or any(
            p in ("__pycache__", ".pytest_cache", ".ruff_cache") for p in Path(name).parts
        ):
            continue
        if not final and matches(name, policy["knowledge_paths"]):
            continue
        path = inside(root, name)
        if path.is_symlink():
            raise HarnessError("path.symlink", "Scope symlink не поддерживается", 1, name)
        digest.update(name.encode() + b"\0")
        digest.update(path.read_bytes() if path.is_file() else b"<deleted-or-absent>")
        digest.update(b"\0")
    return digest.hexdigest()


def evidence_hashes(task: Path, paths: list) -> dict:
    """Связывает факт проверки с неизменным содержимым его evidence файлов."""
    evidence(task, paths)
    return {name: file_hash(inside(task, name)) for name in paths}


def evidence(task: Path, paths: list) -> None:
    """Проверяет непустые реальные файлы evidence внутри выбранной задачи."""
    if not isinstance(paths, list) or not paths:
        raise HarnessError("evidence.required", "Нужно фактическое evidence", 1)
    for name in paths:
        p = inside(task, name)
        if not p.is_file() or p.stat().st_size == 0:
            raise HarnessError("evidence.missing", "Evidence отсутствует или пусто", 1, name)


@contextlib.contextmanager
def lock(task: Path):
    """Держит короткий OS lock, автоматически освобождаемый при смерти writer."""
    p = task / ".state.lock"
    inside(task, p.name)
    with p.open("a+b") as handle:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                if handle.read(1) == b"":
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise HarnessError(
                "write.lock", "Другой writer держит lock; перечитайте state", 3
            ) from error
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic(path: Path, state: dict) -> None:
    """Публикует целый YAML через fsync и replace на том же filesystem."""
    descriptor, temporary = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            yaml.safe_dump(state, handle, allow_unicode=True, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Parser(argparse.ArgumentParser):
    """Приводит parser errors к общему JSON/text контракту."""

    def error(self, message: str) -> None:
        """Преобразует неправильные аргументы в exit 2."""
        raise HarnessError("cli.arguments", message, 2)


def parser(description: str, *, task: bool = False, mutation: bool = False) -> Parser:
    """Создаёт общие flags; mutation-команда обязана получить revision."""
    p = Parser(description=description)
    p.add_argument("--root", default=".")
    p.add_argument("--json", action="store_true")
    if task:
        p.add_argument("--task", required=True)
    if mutation:
        p.add_argument("--expected-revision", type=int, required=True)
    return p


def run(function: Any) -> int:
    """Печатает предсказуемый результат CLI, сохраняя содержательные error codes."""
    try:
        result = function()
        result = {"ok": True, "code": 0, "diagnostics": [], **(result or {})}
    except HarnessError as error:
        result = {"ok": False, "code": error.code, "diagnostics": [error.diagnostic]}
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, RecursionError) as error:
        result = {
            "ok": False,
            "code": 2,
            "diagnostics": [
                {
                    "rule": "schema.type",
                    "path": "",
                    "message": "Невалидная вложенная структура: " + type(error).__name__,
                    "suggested_action": "Сверьте типы и обязательные поля со схемой.",
                }
            ],
        }
    except (OSError, UnicodeError) as error:
        result = {
            "ok": False,
            "code": 3,
            "diagnostics": [
                {
                    "rule": "io.resource",
                    "path": "",
                    "message": type(error).__name__,
                    "suggested_action": "Проверьте доступ к ресурсу.",
                }
            ],
        }
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result["code"]
