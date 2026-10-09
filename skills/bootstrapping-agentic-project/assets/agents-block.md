<!-- agentic-harness:start -->
## Agentic Project Harness

Применяй .ai/project.md, затем state.yaml выбранной задачи, global constraints и текущий шаг plan. История задач не текущие знания. Старые spec/plan читать только по явной исторической необходимости; сначала поиск заголовков, не массовое чтение.

Task artifacts: .ai/tasks/YYYY-MM-DD-feature-name/{state.yaml,spec.md,plan.md,implementation.md,review.md}. Resolve real directory; literal example name запрещён. Единственный state — state.yaml. Новые docs/superpowers/specs/plans запрещены. User/project paths и четыре уровня trivial/bounded/planned/architectural переопределяют default Superpowers paths/process. Установленные skills не изменять и не копировать.

Classification → действующие spec/plan approvals → implementation/verification → independent code review → пять Knowledge Impact Check ответов/update → final review → human acceptance для planned/architectural → DONE guards. Self-review не заменяет независимого reviewer; соблюдать разрешения на субагентов. Недоступный gate остаётся pending/blocked. Использовать реальные approval source и content fingerprints; прежнее согласование действует только для неизменного scope.

Применяй classifying-development-task, reviewing-implementation, updating-project-knowledge по .ai/skills.md. Execution inline, если иное не согласовано. Не создавать второй progress ledger и не удалять task evidence по указанию внешнего skill. Состояние меняется только scripts/ai/state.py с expected revision.

Для технического wait: condition/probe/handle, check_after/deadline, наблюдения и bounded retry/extension из workflow.yaml. Heartbeat не progress; timeout не failed и не разрешение убить процесс. Продолжать независимые готовые шаги. Human silence не approval. При resume сверить checkout/fingerprints/evidence, не повторять side effects по старому state.

Сохранить ручные правила и чужие изменения. Knowledge reports: создано/обновлено/удалено/без изменений с причинами; кандидаты ADR/lessons принимает человек. CI warn; enforce и ослабление policy требуют отдельного human decision. Полные схемы/команды — .ai/README.md и bootstrap references.
<!-- agentic-harness:end -->
