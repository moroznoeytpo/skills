# State workflow v1

created, specifying, waiting_spec_approval, planning, waiting_plan_approval, ready, implementing, verifying, reviewing, updating_knowledge, waiting, blocked, waiting_human, done, failed. Уровень/фаза/step status различаются.

Основной путь: created → ready для trivial, иначе specifying → waiting_spec_approval → ready bounded либо planning → waiting_plan_approval → ready. Ready → implementing → verifying → reviewing(code) → updating_knowledge → reviewing(final) → waiting_human когда требуется → done. Trivial без review: verifying → updating_knowledge → done. Ошибки возвращают нужный этап; новые requirements переводят в specifying и stale approvals.

Technical wait хранит resume_state/step/condition/probe/started_at/check_after/deadline/class/attempts/extensions/last_observation. Нельзя вложенные waits, потерять handle при resume или повторить живой side effect. Blocker сохраняет фактическую исходную фазу; независимый ready step может продолжаться. Human gate не имеет retry/deadline-as-consent. Новый вопрос имеет новый gate_id и требует нового source/current scope.

DONE требует complete steps, текущие spec/plan approvals, verification evidence/content hash, независимый final review и review.md hash, пять knowledge ответов/notification, отсутствие wait/blocker/findings и final human acceptance по уровню. Исторический done при общем scan проверяется на целостность evidence/docs; право покрыть текущий production diff даёт только актуальный scope fingerprint. Explicit --task проверяет и текущее содержимое.

Resume сверяет identity/base, spec/plan, evidence и scope, сохраняет reconciliation. Не исполняет команды. Полные typed fields и guards реализованы в scripts/ai/schema.py; CLI --help и event reference описывают ввод.

Review result не может менять mode текущего раунда: code/final переключается только
предусмотренным переходом. Первичное code changes_requested возвращает implementation;
правка знаний возможна после code pass или final finding. Завершение технического wait
или blocker в waiting_human закрывает только операцию, сохраняя вопрос человеку. Даже
успешный процесс не является human decision. Для prerequisite проверяется весь DAG предков.
