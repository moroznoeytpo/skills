---
name: updating-project-knowledge
description: Выполнить обязательный Knowledge Impact Check после code review или trivial verification и обновить только затронутые актуальные знания.
---

# updating-project-knowledge

Вход: текущий diff, verification и code review, task state, релевантные текущие знания. Читай ../bootstrapping-agentic-project/references/knowledge-lifecycle.md bootstrap package только по необходимости. Для project/architecture/adr/lessons/agent_rules ответь yes/no с основанием; unknown не завершённая проверка.

Project описывает команды/stack/components; architecture — фактическое устройство с evidence, не будущее. ADR сохраняет долговременное решение и human source; исторический кандидат не становится accepted из-за наличия кода. Proposed/deferred/rejected остаются явными. Supersede сохраняет старое решение с двусторонними ссылками. Lessons содержат подтверждённую причину или обозначенную гипотезу и полезное действие; общие советы и разовые логи не нужны.

Если все пять no, не трогай knowledge ради даты; запиши no_change. Иначе адресно обнови документы после нужного human decision, record knowledge_result. Уведоми человека: создано/обновлено/удалено/без изменений, пути и причины; notification хранит фактическое сообщение. Глобальную память не изменять. Выход: impact/rationale/diff/notification; затем final review.
