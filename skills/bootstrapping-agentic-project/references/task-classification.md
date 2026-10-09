# Классификация

Первый подходящий признак: architectural — ownership/boundary/security/concurrency/infrastructure/storage/protocol/significant dependency; planned — API/migration/несколько зависимых компонентов; bounded — behavior/dependency внутри одного компонента; trivial — локальная редакционная правка без перечисленного. Сомнение между соседями — один выше, не бесконечное повышение.

Trivial: state, соразмерная verification, пять knowledge ответов; spec/plan и review не обязательны с причиной not_required. Bounded: short spec approval, implementation/review, independent code/final review. Planned/architectural: полные spec+plan approvals, dependencies, independent review и final human acceptance. Architectural сверяет ADR.

Escalation в той же задаче инвалидирует зависимые approvals и gates; согласовать новый scope до зависимого исполнения. Downgrade только с доказательством сужения, не ради обхода pending architecture gate.
