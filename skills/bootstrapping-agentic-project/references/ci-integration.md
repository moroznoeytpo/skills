# CI integration

Использовать существующий provider; если его нет — локальный эквивалент. Рабочий step после установки requirements-ai.lock:

```sh
python -B scripts/ai/validate.py --all --base "$HARNESS_BASE_REF" --mode warn --json
```

HARNESS_BASE_REF должен быть существующим ref целевой ветки; checkout fetch должен содержать merge base. Missing base — error, не пустой diff. Warn снижает policy violations до warning/exit 0, но parse/I/O остаются ошибками. Enforce тестируется только в fixture; рабочее переключение и branch protection требуют отдельного human decision. Локальный exit 1 не доказывает merge-blocking.
