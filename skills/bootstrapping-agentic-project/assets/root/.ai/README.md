# Agentic Project Harness

## Пять законов

1. **CODE describes implementation.** Код и тесты показывают реализацию; исполнение доказывает evidence.
2. **ARCHITECTURE describes the current system.** Текущее устройство, не будущий план.
3. **ADR explains durable architectural decisions.** Принятое человеком решение, причины и последствия.
4. **TASK artifacts describe one finite piece of work.** Артефакты конечной задачи.
5. **AGENTS.md describes how an agent must operate.** Постоянные правила и routing.

**Task history is not current project knowledge.** Исторические планы не становятся фактами.

## Пять уровней контроля

AGENTS задаёт инструкции; skills — процедуры; state machine — переходы/guards; filesystem tooling — структуру/fingerprints/evidence; CI — проверку перед принятием изменений. Это guardrails и обнаружение нарушений, не физическая изоляция агента с доступом к файлам. Эта установка использует local warn. Конфигурация CI в checkout не найдена; настройки внешней платформы и branch protection не проверены и этой установкой не изменяются.

Начинать с [project.md](project.md), затем выбранного task/state и релевантных знаний. Каталог [skills.md](skills.md). Политика [workflow.yaml](workflow.yaml). Полное чтение старых задач не требуется. Единственный статус задачи — state.yaml.

## Использование

Из root проекта подготовить отдельную dev-среду Python ≥3.11 и установить
`python -m pip install -r requirements-ai.lock`. Это зависимости harness, не runtime.
Существующий `.venv` допускается, если его зависимости совместимы.

```sh
python -B scripts/ai/bootstrap_task.py create --title 'Исправить ссылку README' --slug fix-readme-link --level trivial --reason 'Только ссылка, без изменения поведения' --json
python -B scripts/ai/state.py show --task ИМЯ_ИЗ_CREATE --json
python -B scripts/ai/state.py record --task ИМЯ_ИЗ_CREATE --expected-revision РЕВИЗИЯ_ИЗ_SHOW --event-file ПУТЬ_К_EVENT_JSON --json
python -B scripts/ai/state.py transition --task ИМЯ_ИЗ_CREATE --expected-revision РЕВИЗИЯ_ИЗ_SHOW --to ready --reason 'Scope и prerequisites проверены' --json
python -B scripts/ai/validate.py --all --mode warn --json
python -B scripts/ai/check_stall.py --task ИМЯ_ИЗ_CREATE --json
```

Заменить параметры фактическим именем и ревизией из вывода; shell переменные или пробный
план не считаются выполнением. Для каждого record создать JSON в выбранном task workspace.
Пример `set_steps` для trivial после проверки реальной ссылки:

```json
{
  "event": "set_steps",
  "reason": "Определён единственный изменяемый документ",
  "payload": {
    "scope_paths": ["README.md"],
    "spec_fingerprint": null,
    "plan_fingerprint": null,
    "steps": [{"id": 1, "title": "Исправить ссылку и проверить цель", "depends_on": [], "status": "pending", "verification": "pending", "evidence": []}]
  }
}
```

Дальше implementing → step_started → фактическое изменение/проверка → step_result →
verifying → verification_result. Для trivial reviewing может быть not_required с причиной;
обязательный updating_knowledge включает пять ответов и реальное уведомление. Для bounded
перед исполнением требуется short spec approval, после verification независимый code review,
knowledge check и final review. Planned/architectural добавляют plan approval и итоговую
приёмку человеком. Architectural решения предъявляются человеку, а не принимаются по наличию кода.

Полный ввод: [typed events](../.agents/skills/bootstrapping-agentic-project/references/event-schema.md),
[переходы](../.agents/skills/bootstrapping-agentic-project/references/workflow-states.md),
[классификация](../.agents/skills/bootstrapping-agentic-project/references/task-classification.md).
`state.py show` выдаёт актуальные code/final/spec/plan fingerprints; это идентификаторы
содержимого, не доказательство проверки. Evidence необходимо получить фактическим запуском.

## Продолжение и ожидания

Начать с state выбранной задачи и `state.py resume --task ... --expected-revision ...`.
При stale перечитать причину, проверить сохранённый код и повторить затронутую проверку.
Не повторять процесс или внешний side effect, пока не проверены handle/логи прежней операции.
При technical wait записать condition, безопасное описание probe/handle, сроки и timeout class.
`check_stall.py` ничего не запускает; он возвращает диагностику. Продление требует evidence
содержательного прогресса и ограничено workflow policy. Ответ человека не имеет автоматического
deadline-as-consent. Независимый шаг можно продолжить при сохранённом blocker другого ID.

Выход CLI: 0 — успех (в warn возможны policy diagnostics), 1 — policy/gate нарушение,
2 — формат/схема/CLI, 3 — I/O, Git base или конфликт revision. После ошибки не править state
вручную; перечитать вывод. Исторические done задачи не должны блокировать новый diff, но только
свежая завершённая задача может покрыть изменённые production paths.

## Перенос

Скопировать целиком `.agents/skills/bootstrapping-agentic-project/` в другой проект либо
отдельный каталог. Через интерпретатор Python с PyYAML выполнить его `scripts/install.py`
с `--root <целевой-root> --mode audit --json`. После конкретного согласования использовать
`--mode install`; `--dry-run` не пишет. `--mode update` сохраняет ручные экземпляры и выдаёт
адресные conflicts/diff, которые нужно разрешить отдельно; повторный install не дублирует markers.
Проверить `scripts/validate.py --root <целевой-root> --json`, затем повторить A/B/C по коду
нового проекта. Реальные знания/ADR/tasks исходного проекта в payload не входят. Подробности:
[bootstrap](../.agents/skills/bootstrapping-agentic-project/SKILL.md).
