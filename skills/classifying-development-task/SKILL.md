---
name: classifying-development-task
description: Классифицировать новую задачу или пересмотреть уровень при изменении scope и записать признаки и gates в task state.
---

# classifying-development-task

Вход: запрос, применимые AGENTS, .ai/project.md, выбранный task state и затронутый код. Прочитай ../bootstrapping-agentic-project/references/task-classification.md bootstrap package. Проверь признаки сверху вниз: boundary/security/ownership/concurrency/storage/protocol/существенная dependency → architectural; migration/API/несколько зависимых компонентов → planned; behavior/dependency внутри компонента → bounded; только отсутствие всех признаков даёт trivial. Размер diff не критерий. Соседнее сомнение — один уровень выше.

Создай задачу bootstrap_task.py create, затем record classify и set_steps. Все пути repo-relative. Escalation сохраняет task/history, invalidates approvals; dependent implementation ждёт нового согласования, независимая работа продолжается. Downgrade требует доказанного сужения и не обходит architecture question. Выход: state classification/reason/signals, нужные документы/gates и next_action. Ошибки schema/path/revision не исправлять прямой записью YAML; перечитай state и diagnostics.
