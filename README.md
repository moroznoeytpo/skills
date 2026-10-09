# Agentic Project Harness skills

Четыре переносимых навыка Codex, вынесенные из ERAMCO без изменения инструкций.

- `bootstrapping-agentic-project` — audit/install/update harness; включает templates, references и tooling.
- `classifying-development-task` — классификация задачи и необходимые gates.
- `reviewing-implementation` — независимое code/final review.
- `updating-project-knowledge` — Knowledge Impact Check и обновление текущих знаний.

## Персональная установка

Исходники живут отдельно от прочих личных навыков:

```sh
git clone https://github.com/moroznoeytpo/skills.git ~/.codex/skill-repositories/skills
```

Из `skills/` создайте четыре ссылки с соответствующими именами в `~/.codex/skills/`.
Не заменяйте существующие каталоги или ссылки без сравнения. Соседние ссылки сохраняют относительные references между навыками. После изменения состава начните новую сессию Codex; чтение файла не доказывает автоматическое discovery.

Свежий Codex `skills/list` обнаруживает навыки с префиксом `agentic-project-harness:`, например `agentic-project-harness:classifying-development-task`; canonical пути указывают на этот checkout после разрешения ссылок.

Обновление: `git -C ~/.codex/skill-repositories/skills pull --ff-only` после проверки локального status. Не редактируйте plugin cache.

## Плагин Codex

`.codex-plugin/plugin.json` объявляет пакет, `.agents/plugins/marketplace.json` — каталог с одним плагином.
Подключение сервиса GitHub даёт доступ к файлам репозитория; установка skills-плагина выполняется отдельно через Plugins Directory/marketplace.

```sh
codex plugin marketplace add moroznoeytpo/skills
```

После добавления выберите Agentic Project Harness в Plugins Directory и установите его.
На одном устройстве выберите один способ загрузки: персональные ссылки либо установленный плагин, чтобы не создавать дубликаты.

## Проверки

Python >=3.11; отдельное dev-окружение с `requirements-dev.lock`:

```sh
python -m pip install -r requirements-dev.lock
python -B -m pytest -q tests
ruff check .
ruff format --check .
```

Тесты проверяют реальную установку в disposable проекты, idempotence, сохранение ручных файлов, path containment и отказ неполного пакета до записи. Исходные skills и assets не зависят от checkout ERAMCO. Installer по-прежнему создаёт самостоятельные project skills в целевом проекте; глобальная загрузка не устанавливает harness автоматически.

[Формат плагина Codex](https://developers.openai.com/plugins/build/plugins).
