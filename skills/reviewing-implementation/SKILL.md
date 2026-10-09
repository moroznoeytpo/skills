---
name: reviewing-implementation
description: Независимо проверить реализацию после verification либо подготовленные знания после knowledge update; записать code/final review и findings.
---

# reviewing-implementation

Вход: spec, plan/global constraints, реальный diff, текущие fingerprints, test evidence, релевантные architecture/ADR. Не принимать reasoning/итог автора как доказательство. Reviewer — отдельный разрешённый исполнитель с чистым контекстом либо человек. При недоступности подготовь пакет и оставь gate blocked/pending; self-review не substitute.

В mode code проверь полноту требований, regression/scope, boundaries, лишние abstractions и качество evidence. В mode final сверяй code fingerprint и knowledge diff; при неизменном коде не повторяй полный review/tests без причины. Читай ../bootstrapping-agentic-project/references/workflow-states.md по необходимости.

Выход: review.md с identity/date/mode/scope/fingerprint, findings ID/severity/location/evidence/expected_fix/status/resolution, limitations/verdict; record review_result. Critical/major open блокируют passed; accepted_risk требует человека. Minor исправлен или явно диспозирован, suggestion не расширяет scope. Исправления инвалидируют соответствующий gate и требуют актуальной перепроверки. Code pass открывает updating_knowledge, final pass — human gate/terminal guards.
