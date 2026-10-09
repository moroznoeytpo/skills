# Typed events v1

UTF-8 JSON envelope: event, reason, payload. Запись задаёт время; evidence имеет собственные даты. Любая мутация требует --expected-revision. Unknown event/arbitrary patch запрещены. State schema v1, enum строки; yes/no и даты в YAML явно строки.

| Event | Required payload |
|---|---|
| classify | level, reason, signals |
| set_steps | plan_fingerprint, scope_paths, spec_fingerprint, steps |
| step_started | step_id |
| step_result | evidence, status, step_id, verification |
| verification_result | evidence, limitations, requirements_fingerprints, scope_fingerprint, status |
| review_result | evidence, findings, independent, mode, requirements_fingerprints, reviewer, scope_fingerprint, status |
| approval | decided_at, kind, scope_fingerprint, scope_summary, source, status |
| knowledge_result | changes, impact, notification, rationale, status |
| progress_observed | evidence, meaningful, observation, observed_at |
| wait_started | attempts, check_after, condition, deadline, extensions, kind, last_observation, probe, resume_state, started_at, step_id, timeout_class |
| wait_extended | evidence, new_deadline, reason |
| wait_resolved | evidence, result |
| blocker_recorded | attempts, expected, investigation, likely_cause, next_action, observed, resume_state, step_id |
| blocker_resolved | evidence, resolution, step_id |
| checkpoint | evidence, next_action, summary |

Фазы: classify/checkpoint/progress — незавершённые; set_steps — created/specifying/planning; step_started — implementing или технический waiting с resume_state=implementing; step_result — те же фазы либо verifying; verification_result — verifying; review_result — reviewing; knowledge_result — updating_knowledge; approval — соответствующая подготовка/human gate; wait/blocker — фактическая нетерминальная фаза и связанные события только при существующем ожидании.

Результаты автоматически сохраняют evidence_hashes; review также hash review.md. Requirements hashes передаются вместе с scope hash из state.py show. Не подделывать человеческие источники. Для общего human вопроса checkpoint допускает human_decision с source, decided_at, gate_id, scope_fingerprint, resume_state: это не spec/plan/final approval и не обходит DONE. Wait retry требует prior_terminated_evidence и следующий attempts; максимум policy. Failed recovery — transition с причиной в ready/specifying/planning, после reconciliation. Done обычным transition не открывается; несогласованное завершение требует явного решения, не автопочинки.

`step_result` дополнительно допускает `scope_paths`: конкретные файлы результата этого шага.
Без него используется task scope. Evidence hashes сохраняются всегда. Перед запуском зависимого
шага проверяется содержимое prerequisites; если оно изменено, resume переводит затронутые
результаты в pending/stale. Scope должен описывать фактический результат, его достаточность
проверяет reviewer. Независимое изменение другого файла не отменяет проверку первого.

`set_steps` при незакрытой операции сохраняет её шаг без изменения ID/status/dependencies.
Нельзя запускать ID активного wait/blocker повторно. `wait_resolved` сохраняет operation_result
с handle и evidence; completed процесс не означает done шага. При stale dependencies шаг
остаётся pending, его процесс не нужно автоматически запускать снова. Escalation сохраняет
handle и переводит разрешённую фазу возврата в specifying. Отказ final approval разрешает
возврат на исправление с сохранённым source, но не отменяет spec/plan prerequisites.

Во время технического wait можно запустить один независимый готовый шаг и записать его
результат, сохраняя wait/handle. Ожидаемый шаг и его dependents запускать нельзя. Сначала
завершить независимый running шаг, затем регистрировать wait_resolved; human gate этим
исключением не обходится.
