---
name: bootstrapping-agentic-project
description: Установить, обновить или провести read-only аудит Agentic Project Harness в существующем проекте с сохранением ручных инструкций и извлечением актуальных знаний.
---

# Bootstrapping Agentic Project

Вход: запрос install/update/audit, существующий проект и его инструкции. Выбери настоящий root, Git/checkout/status/overrides, существующие skills и CI. При неоднозначности уточни root до записи. Общая концепция не заменяет одобрение конкретного аудита.

1. Прочитай references/bootstrap-process.md и references/install-update-policy.md. Audit перед изменениями: команды/архитектура/history/ограничения, точные пути и предлагаемый diff. Покажи для согласования; уже данное согласование этого scope не повторять.
2. `scripts/install.py --root ROOT --mode audit --json`, затем разрешённый install/update. `--dry-run` не пишет. Конфликтующие ручные files/marker contents сохранить и предъявить patch; не менять глобальные skills/settings/Superpowers. Новый CI provider не добавлять.
3. Определи dev runtime/YAML parser по проекту, закрепи зависимости; создай конечную bootstrap task в .ai/tasks с единственным state.yaml. Spec/plan/approvals должны быть реальными. До runtime helpers initial state создаётся однократно по assets/templates/state.yaml и затем валидируется.
4. A inventory: manifests/entrypoints/tests/CI/settings; project.md с command cwd/prerequisites/execution status. B current architecture с code/symbol evidence и confirmed/inferred/unknown. C кандидаты ADR/lessons в task implementation.md: ID/context/evidence/confidence/uncertainty/relevance/question; human accepted/rejected/deferred. Не копировать знания предыдущего проекта. Не создавать accepted ADR на A или из старого плана.
5. Классификация и gates: references/task-classification.md, workflow-states.md, event-schema.md. Каталог skills — реальные available/missing/unverified. Проверить discovery в свежей сессии; чтение SKILL не доказывает автоматического обнаружения. Superpowers path override проверить реальным использованием, без fork/adapter по предположению.
6. `scripts/validate.py --root ROOT --json`; installed scripts/ai/validate.py, реальные сценарии, code review → Knowledge Impact Check/update → final review → human acceptance. Пять уровней контроля не гарантируют физическую невозможность обхода процесса. CI warn; enforce рабочего проекта требует отдельного решения.

Выход: работающий tooling и package, актуальные знания, task/evidence и честный отчёт по AUTO/SESSION/REVIEW/CI/external. Непройденное не PASS, done только при guards. При wait — наблюдение/срок/диагностика и next_action, никакого вечного polling. Независимые разрешённые этапы продолжаются при ожидающем human decision.
