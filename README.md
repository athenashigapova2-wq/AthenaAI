# Athena AI

Athena AI — мобильное приложение для питания, тренировок и восстановления с
персональным AI-агентом. Интерфейс построен на React и Capacitor, серверная часть —
на FastAPI, LangGraph, Redis и Celery. Единственная облачная LLM проекта — GigaChat.

Поддерживаемые языки: русский, английский, французский, испанский и китайский.

## Возможности

- онбординг и расчёт целевых калорий и БЖУ;
- дневник питания и семантический поиск по справочнику продуктов;
- история и запись тренировок;
- данные сна, энергии, веса и цикла;
- AI-чат с маршрутизацией по specialist-агентам;
- потоковые статусы AI-job через SSE и отмена выполняющегося ответа;
- многоуровневая память диалога: recent messages, rolling summary и проверенные предпочтения;
- RAG по проверенной базе знаний с каноническими ссылками;
- трассировка LLM/tool calls и offline-eval сценарии на пяти языках.

## Архитектура

```text
React / Vite / Capacitor
        │ Supabase JWT
        ▼
FastAPI :8001
  ├─ /agent/chat ─► Redis ─► Celery ─► LangGraph
  └─ /ai/tasks/{task} ───────────────────────┐
                                             ▼
                                 AIExecutionService
                     routing → privacy → resilience → tracing
                                             │
                                             ▼
                                         LLMGateway
                                      ├─ GigaChat
                                      └─ future providers

Supabase Edge Functions: barcode lookup / Supabase-specific deterministic work
```

В Docker запускаются три сервиса:

| Сервис | Назначение |
|---|---|
| `api` | FastAPI, JWT boundary, постановка заданий и выдача статуса |
| `redis` | Celery broker и краткоживущее хранилище job status/result |
| `worker` | Выполнение LangGraph, GigaChat, RAG и инструментов |

Frontend в локальной разработке запускается отдельно через Vite на порту `5175`.

### Поток сообщения

1. Frontend отправляет `POST /api/v1/agent/chat` с Supabase access token.
2. FastAPI проверяет JWT, создаёт job в Redis и возвращает `202` с `job_id`.
3. Celery worker получает задание из очереди `athena-agent`.
4. Router выбирает `nutrition`, `workout`, `recovery` или `general`.
5. Retriever добавляет релевантный RAG-контекст.
6. Specialist вызывает GigaChat и доступные ему инструменты.
7. API передаёт состояния `queued → running → tool_call → generating → completed`
   через SSE endpoint `/chat/jobs/{job_id}/events`.
8. Результат сохраняется в Redis и Supabase; frontend закрывает SSE-соединение и
   обновляет разговор. Пользователь может остановить запрос через
   `POST /chat/jobs/{job_id}/cancel`.

Frontend использует `AbortController`, поэтому отмена закрывает соединение и
отправляет cooperative cancellation backend. Redis хранит авторитетное состояние
отмены, а Celery worker проверяет его между этапами выполнения.

### Память разговора

В prompt передаются не последние 20 сообщений целиком, а четыре слоя контекста:

- ограниченное число свежих сообщений текущего разговора;
- rolling `conversation_summary`;
- структурированные `learned_preferences`, `avoided_foods` и `successful_meals`;
- актуальное состояние пользователя из доверенных серверных данных.

После успешного ответа отдельный structured extraction предлагает обновления
памяти. Сервер принимает только факты выше порога confidence, валидирует и
объединяет их с существующей памятью. Чтение и обновление памяти работают
best-effort: отказ Supabase на этом пути не должен менять уже полученный ответ.

### Границы инструментов

`user_id` берётся только из проверенного JWT и замыкается внутри tool-функций. Он
не входит в JSON Schema, которую видит модель. Каждый specialist получает только
свой набор инструментов:

- Nutrition: профиль, поиск еды, дневной рацион, запись еды;
- Workout: профиль, история и запись тренировок;
- Recovery: профиль, сон, энергия, вес и цикл;
- General: ответ без записывающих инструментов.

`log_meal` и `log_workout` выполняются только после явной просьбы пользователя.

## Надёжность

### Безопасные retries

Повторяются только идемпотентные операции:

- вызовы GigaChat;
- чтение истории разговора;
- RAG RPC;
- инструменты, явно отмеченные `read_only`.

Для network/timeout и HTTP `408`, `425`, `500`, `502`, `503`, `504` по умолчанию
выполняется до трёх попыток с exponential backoff `0.5s → 1s`, jitter до 25% и
верхней границей задержки 4 секунды. HTTP `429` использует более спокойную отдельную
политику: до четырёх попыток с задержками `2s → 4s → 8s`, jitter и учётом числового
заголовка `Retry-After` (с общей верхней границей 30 секунд).

Операции записи и Celery-задача целиком не повторяются: это предотвращает двойную
запись еды или тренировки при неопределённом результате сетевого запроса.

### Redis rate limiter для GigaChat

Перед каждой фактической попыткой GigaChat worker получает permit из общего Redis
token bucket. Поэтому четыре Celery threads и дополнительные worker-контейнеры не
создают независимые всплески к провайдеру. По умолчанию общий лимит равен `4 RPS`,
разрешённый кратковременный burst — 4 запроса, ожидание permit — до 30 секунд.

Лимитер применяется только к реальным GigaChat-вызовам: mock LLM, Supabase reads и
write-инструменты через него не проходят. Permit получается до создания строки
`agent_llm_calls`, поэтому ожидание не считается provider latency и не выглядит как
несуществующая попытка. Если Redis недоступен, limiter работает fail-open и пишет
warning; если permit не получен за timeout, provider не вызывается и состояние
circuit breaker не изменяется.

Параметры `LLM_RATE_LIMIT_*` нужно согласовать с квотой конкретного GigaChat-контракта.
Текущее состояние bucket можно посмотреть без изменения данных:

```powershell
docker compose exec -T redis redis-cli `
    GET athena:rate-limit:gigachat
```

### Конфигурируемый model router

В production-режиме model router выбирает только между настроенными моделями
GigaChat; runtime-переключения на другого облачного провайдера нет. Доступны два tier:

- `small` — `LLM_ROUTER_MODEL`, а если он пустой, используется `GIGACHAT_MODEL`;
- `main` — `GIGACHAT_MODEL`.

Policy задаётся JSON-объектом в `LLM_MODEL_ROUTING_POLICY`. Правила проверяются в
порядке `node.purpose → node.* → *.purpose → *`. Конфигурация по умолчанию отправляет
классификацию маршрута и перевод названия продукта в `small`, а остальные вызовы —
в `main`:

```env
LLM_MODEL_ROUTING_ENABLED=true
LLM_ROUTER_MODEL=
LLM_MODEL_ROUTING_POLICY={"router.route_classification":"small","nutrition.food_translation":"small","*":"main"}
```

Примеры `node`: `router`, `nutrition`, `workout`, `recovery`, `general`. Примеры
`purpose`: `route_classification`, `food_translation`, `tool_planning_or_answer`,
`answer`. Неизвестный или некорректный tier останавливает backend при чтении настроек;
молчаливого provider fallback нет. Фактические `model_tier` и `model_name` каждого
вызова сохраняются в `agent_llm_calls`.

Каждая фактическая попытка обращения к GigaChat создаёт отдельную строку
`agent_llm_calls`. Все retries одного логического вызова объединяет `invocation_id`,
а `attempt_number` содержит номер попытки. Для аудита также сохраняются:

- `requested_model_tier` и фактически использованный `model_tier`;
- `routing_rule` и человекочитаемый `selection_reason`;
- `is_fallback` и `fallback_reason`;
- `retry_reason` — классификация ошибки предыдущей попытки.

Если policy выбрала `small`, но `LLM_ROUTER_MODEL` пустой, используется main-модель и
это явно записывается как fallback. Runtime/provider fallback не выполняется. Перед
запуском этого backend-кода должна быть применена миграция
`0015_agent_llm_attempt_tracing.sql`.

### Детерминированный mock LLM

Для локальной проверки FastAPI, Redis, Celery, LangGraph и longitudinal-тестового
контура можно явно включить mock-модель:

```env
LLM_PROVIDER=mock
MOCK_LLM_MODEL=athena-mock-v1
MOCK_LLM_LATENCY_MS=0
```

По умолчанию используется `LLM_PROVIDER=gigachat`. Mock не является fallback,
никогда не обращается к GigaChat и помечается как `model_provider=mock` в tracing.
Он возвращает детерминированные ответы и нужен для проверки инфраструктуры, а не
для оценки качества реальной модели. JWT, Supabase и остальные границы доступа
при этом не отключаются. После изменения `.env` пересоздайте `api` и `worker`.

Для поиска именно инфраструктурного предела FastAPI → Redis → Celery → Redis
есть отдельный, явно включаемый режим:

```env
LLM_PROVIDER=mock
AGENT_INFRASTRUCTURE_TEST_MODE=true
AGENT_INFRASTRUCTURE_TEST_LATENCY_MS=0
```

В нём API по-прежнему проверяет JWT, создаёт Redis job и отправляет Celery task,
а worker записывает результат обратно в Redis. Внутри worker не вызываются
LangGraph, Supabase и внешний LLM. Режим не запустится с
`LLM_PROVIDER=gigachat`. После теста обязательно верните
`AGENT_INFRASTRUCTURE_TEST_MODE=false`.

Ступенчатый capacity-тест запускается так:

```powershell
.\backend\load_tests\jmeter\run-capacity-with-grafana.ps1
```

По умолчанию выполняются ступени 10, 20, 40, 80 и 120 виртуальных пользователей.
Для каждой ступени сохраняются JTL, JSON summary, p50/p95/p99 полного E2E,
latency постановки задачи в очередь, throughput и error rate. Общий CSV/JSON
создаётся в `%TEMP%\athena-jmeter-capacity-results-*`.

После миграции `agent_runs.llm_call_count` означает число фактических provider-попыток,
а не число логических вызовов. Последние решения можно проверить в SQL Editor:

```sql
select invocation_id, attempt_number, node_name, purpose,
       requested_model_tier, model_tier, model_name,
       routing_rule, selection_reason, is_fallback,
       fallback_reason, retry_reason, status
from public.agent_llm_calls
order by created_at desc
limit 50;
```

### Redis circuit breaker

Все workers используют общий circuit breaker GigaChat в Redis. После пяти логических
временных сбоев (каждый считается только после исчерпания retries) circuit переходит
из `closed` в `open`. Следующие LLM-вызовы завершаются сразу, не создавая дополнительную
нагрузку на недоступного провайдера.

Через 30 секунд circuit атомарно переходит в `half_open`: только один worker получает
lease на пробный вызов. Успешный probe закрывает circuit и сбрасывает счётчик; временная
ошибка снова открывает его. Если worker погиб во время probe, 210-секундный lease
освобождается автоматически. Lua-скрипты и Redis `TIME` обеспечивают одинаковое
состояние и единственный probe при нескольких контейнерах worker.

При недоступности Redis breaker работает fail-open: GigaChat-вызов разрешается, чтобы
защитный механизм сам не стал причиной отказа. Ошибки запроса, авторизации и другие
не-временные ошибки не увеличивают счётчик availability failures.

Текущее состояние можно посмотреть без изменения данных:

```powershell
docker compose exec -T redis redis-cli `
    HGETALL athena:circuit-breaker:gigachat
```

Отсутствующий ключ означает `closed`. Параметры порога, cooldown, probe lease и TTL
задаются переменными `LLM_CIRCUIT_BREAKER_*` из `backend/.env.example`.

### Embedding model

Worker до перехода в `ready` загружает локальную модель
`intfloat/multilingual-e5-base`. Файлы сохраняются в Docker volume `hf-cache`,
поэтому пересоздание контейнера не требует повторного скачивания. Инициализация
защищена lock и выполняется один раз при четырёх worker threads.

### Health checks

- `/health` — процесс FastAPI работает;
- `/health/ready` — заданы обязательные настройки и доступен Redis;
- worker healthcheck — Celery отвечает на `inspect ping`;
- Redis healthcheck — `redis-cli ping`.

## Стек

**Frontend:** React, Vite, Tailwind CSS, Capacitor, Supabase JS.

**Backend:** Python 3.11, FastAPI, LangChain Core, LangGraph, GigaChat, Celery.

**Data:** Supabase PostgreSQL, pgvector, Row Level Security, Redis.

**ML:** GigaChat и локальная `multilingual-e5-base` для embeddings.

## Требования

- Node.js 20+ и npm;
- Python 3.11;
- Docker Desktop с Linux Engine;
- проект Supabase;
- GigaChat Authorization key.

## Настройка окружения

### Frontend

```powershell
Copy-Item ".\.env.example" ".\.env"
npm install
```

Заполните корневой `.env`:

```env
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
VITE_AGENT_API_URL=https://your-production-api.example.com
AGENT_PROXY_TARGET=http://127.0.0.1:8001
```

`VITE_`-переменные попадают в клиентский bundle. Никогда не помещайте туда
`service_role` или GigaChat Authorization key.

### Backend

```powershell
python -m venv .venv
& ".\.venv\Scripts\Activate.ps1"
python -m pip install -r ".\backend\requirements.txt"
Copy-Item ".\backend\.env.example" ".\backend\.env"
```

Минимальная конфигурация `backend/.env`:

```env
GIGACHAT_AUTH_KEY=
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_MODEL=GigaChat-2
LLM_ROUTER_MODEL=
LLM_MODEL_ROUTING_ENABLED=true
LLM_MODEL_ROUTING_POLICY={"router.route_classification":"small","nutrition.food_translation":"small","*":"main"}

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET=
SUPABASE_JWT_AUDIENCE=authenticated

API_CORS_ORIGINS=http://localhost:5175,http://127.0.0.1:5175
REDIS_URL=redis://127.0.0.1:6379/0
```

`SUPABASE_JWT_SECRET` нужен только проектам с legacy HS256-токенами. Для
RS256/ES256 backend получает публичные ключи из Supabase JWKS.

Дополнительные настройки retries и RAG перечислены в
[`backend/.env.example`](backend/.env.example).

## Supabase migrations

Примените миграции из `supabase/migrations/` строго по имени:

```powershell
npx supabase login
npx supabase link --project-ref <project-ref>
npx supabase db push
```

Если Supabase CLI не используется, выполните все миграции по порядку через
Dashboard → SQL Editor.

## Запуск через Docker Compose

Рекомендуемый способ запуска backend:

```powershell
docker compose up -d --build
docker compose ps
```

Ожидаемый результат:

```text
athenaai-api-1      healthy
athenaai-redis-1    healthy
athenaai-worker-1   healthy
```

Проверка API:

```powershell
Invoke-RestMethod "http://127.0.0.1:8001/health"
Invoke-RestMethod "http://127.0.0.1:8001/health/ready"
```

Проверка worker:

```powershell
docker compose exec -T worker python -m celery `
    -A app.workers.celery_app:celery_app `
    inspect ping --timeout=5
```

Логи:

```powershell
docker compose logs -f api worker
```

Остановка без удаления данных:

```powershell
docker compose down
```

`docker compose down --volumes` удаляет очередь Redis и кэш embedding-модели;
используйте команду только для намеренного полного сброса.

Подробности ручного запуска Redis и Celery находятся в
[`backend/WORKERS.md`](backend/WORKERS.md).

## Запуск frontend

В отдельном PowerShell:

```powershell
npm run dev -- --host 127.0.0.1 --port 5175
```

Откройте:

- приложение: <http://127.0.0.1:5175/>;
- AI-чат: <http://127.0.0.1:5175/chat>;
- readiness через Vite proxy: <http://127.0.0.1:5175/agent-api/health/ready>.

В dev-режиме Vite проксирует `/agent-api` на `127.0.0.1:8001`, поэтому локальный
чат не зависит от CORS.

## Проверки

### Frontend unit/component tests

Vitest выполняется в `jsdom`; React-компоненты проверяются через React Testing
Library, `@testing-library/user-event` и `@testing-library/jest-dom`:

```powershell
npm run test:ui
```

Текущий набор проверяет форму входа, доступность composer, защиту от повторной
отправки, SSE lifecycle, истёкшую сессию и ошибку Redis/worker. Тесты не требуют
запущенных Docker-контейнеров и не обращаются к реальным Supabase или GigaChat.

### Browser E2E

Playwright запускает production-сборку приложения в Chromium. Supabase Auth/REST,
FastAPI enqueue/SSE/cancel и внешние функции заменяются детерминированными сетевыми
mock-ответами, поэтому тесты воспроизводимы и безопасны для CI.

Один раз установите Chromium:

```powershell
npx playwright install chromium
```

Запуск критических сценариев:

```powershell
npm run test:e2e
```

Интерактивная отладка:

```powershell
npm run test:e2e:ui
```

Покрыты `login → onboarding → chat`, meal logging, expired JWT, отказ
Redis/worker, duplicate submission, переключение разговоров, mobile viewport и
автоматическая проверка серьёзных accessibility-нарушений через Axe. Production
сборка и локальный E2E-сервер запускаются и завершаются автоматически.

Сценарий подтверждения write-tool пока отмечен `fixme`: текущий Celery-контракт
выполняет write tool до того, как клиент может подтвердить действие. Тест следует
включить после появления server-side confirmation token/endpoint; пропуск нельзя
считать подтверждением безопасности этой цепочки.

### Backend и AI checks

Offline-проверки не обращаются к GigaChat и не изменяют Supabase:

```powershell
python backend/scripts/test_fastapi.py
python backend/scripts/test_agent_architecture.py
python backend/scripts/test_agent_workers.py
python backend/scripts/test_agent_traces.py
python backend/scripts/test_retry_policy.py
python backend/scripts/test_rate_limiter.py
python backend/scripts/test_circuit_breaker.py
python backend/scripts/test_model_routing.py
python backend/scripts/test_rag_retriever.py
python backend/scripts/test_load_tests.py
```

Evaluation datasets:

```powershell
python backend/scripts/eval_agents.py
python backend/scripts/eval_tool_selection.py
python backend/scripts/eval_write_safety.py
python backend/scripts/eval_answer_quality.py
```

Команды с `--live` выполняют реальные вызовы GigaChat, но используют фиктивные
результаты инструментов и не должны записывать пользовательские данные.

GitHub Actions автоматически запускает backend `pytest`/Ruff/mypy/migration
checks, frontend ESLint/typecheck/Vitest/build, отдельный Playwright Chromium job,
offline AI regressions и Docker build. Playwright HTML report сохраняется как
artifact при ошибке. Live GigaChat regression остаётся только manual/scheduled и
требует repository secret `GIGACHAT_AUTH_KEY`.

### Privacy и observability

Trace payloads проходят формальный lifecycle: **redaction → retention → export
→ deletion**. Content управляется одним явным переключателем:

```env
TRACE_CONTENT_MODE=off       # production-safe default
TRACE_CONTENT_MODE=redacted  # classified fields removed before persistence
TRACE_CONTENT_MODE=full      # accepted only in local/dev/test
```

При `off` prompt, response, tool arguments/results и подробный текст ошибок не
сохраняются. Production trace содержит только структурированные поля: run/user
ownership и pseudonymous actor id, conversation, route, provider/model/tier,
status, latency, token usage, retry/fallback metadata, tool name/status,
evaluation scores и timestamps.

Observability 2.0 использует один server-generated `trace_id` на всём пути:
HTTP response/header → Redis job → Celery argument → LangGraph state → tool call
→ каждый LLM attempt. Для chat runs `agent_runs.id` является этим canonical
`trace_id`, а `job_id` хранится отдельно для correlation с очередью.

Миграция `0022_observability_2_slo_metrics.sql` добавляет metadata-only измерения
queue/provider/RAG latency, retrieval hit/count/similarity/context size и
агрегированный eval score. View `agent_slo_metrics_hourly` публикует success rate,
p50/p95/p99, tokens, retry/fallback rate, queue/provider latency, RAG и eval
метрики по часу, route и модели.

Evaluation experiments работают без клиентского A/B-переключателя. Backend
детерминированно назначает authenticated user в вариант из version-controlled
JSON registry и переносит `experiment_id`, `variant_id`, assignment bucket и
config hash вместе с trace. Вариант может менять только allowlisted server
policy (`model_tier`, `temperature`) и содержит optional pricing snapshot.
`agent_experiment_comparison` сравнивает варианты по quality, success,
p50/p95/p99 latency, tokens, retry/fallback, queue/provider latency и estimated
cost с явным `cost_coverage_percent`. Настройка и процедура запуска описаны в
`backend/experiments/README.md`.

Tool calls в этом режиме сохраняют `arg_schema_version`, число аргументов,
результат `success|empty|error` и best-effort `result_row_count`, но не названия и
не значения аргументов. Например, `get_weight_trend` может иметь `arg_count=3` и
`result_row_count=12`, не раскрывая вес, калории или медицинские данные.

Перед любой записью работает единый sanitizer с классификациями `public`,
`internal`, `personal`, `sensitive`, `restricted`. Profile и conversation
payloads считаются sensitive; tool args/results классифицируются по полям.
`redacted` не хранит свободный текст разговора и удаляет personal/sensitive
значения, а credentials (`restricted`) не сохраняются даже в локальном `full`.
В БД вместе с допустимыми metadata записываются classification labels и версия
redactor, чтобы политику можно было аудитировать.

Сырые payloads хранятся не более `TRACE_RAW_PAYLOAD_RETENTION_DAYS` (по умолчанию
7 дней), структурированные trace records — `TRACE_RECORD_RETENTION_DAYS` (90
дней). Ежедневная retention-задача:

```powershell
python backend/scripts/purge_agent_traces.py
```

Аутентифицированный пользователь может экспортировать или удалить только свои
данные через `GET /api/v1/agent/privacy/traces/export` и
`DELETE /api/v1/agent/privacy/traces`. Дочерние tool/LLM traces удаляются
каскадно.

Браузерные AI-задачи используют только
`POST /api/v1/ai/tasks/{use_case}` с JWT, серверным allowlist use cases и
фиксированными Pydantic schemas. Диалоговый агент использует canonical path
FastAPI → Redis/Celery → LangGraph. Все Python use cases входят в единый
`AIExecutionService`, который применяет routing → privacy → resilience → tracing
и только затем вызывает provider через `LLMGateway`. `backend/app/llm.py`
занимается исключительно созданием provider clients. Клиент не может передать
произвольный prompt, model или schema.

Edge Functions не знают LLM provider key и не выполняют inference. Там допустимы
barcode lookup, Supabase-specific операции, небольшие детерминированные
трансформации и thin authenticated proxies без вызова модели. Исходники
`athena-task`, `invoke-llm`, `chat-with-coach`, `estimate-meal` и
`analyze-habits` удалены; ранее deployed функции нужно отдельно удалить через
Supabase CLI, поскольку удаление каталога не undeploy-ит облачный endpoint.

Retrieval-backed оценка блюда теперь живёт в Python как
`MealEstimationService`: `parse_description → retrieve_candidates →
rerank_candidates → calculate_macros`. Только parsing и reranking используют
canonical routed LLM gateway; кандидаты берутся из `food_nutrients`, а КБЖУ
рассчитываются детерминированно. Анализ привычек разделён на детерминированный
`HabitAnalyticsService` и текстовый `HabitInsightGenerator`. HTTP-контракты:
`POST /api/v1/nutrition/meal-estimate` и
`POST /api/v1/nutrition/habit-insight`.

## Нагрузочное тестирование

Locust-сценарий измеряет параллельных пользователей, enqueue и полный цикл worker,
RPS, error rate, p50/p95/p99, а также отдельные стадии warm-up, steady, overload и
recovery. Он делает реальные GigaChat-вызовы и предназначен только для локальной
или staging-среды с отдельными тестовыми пользователями.

Инструкции по токенам, профилю нагрузки, HTML/CSV-отчётам и SLO-проверке находятся
в [`backend/load_tests/README.md`](backend/load_tests/README.md).

## RAG и справочник продуктов

Runtime-путь RAG: `router → retriever → specialist`. Документация ingestion,
лицензирования источников и формата bundles находится в
[`backend/knowledge/README.md`](backend/knowledge/README.md).

Основные команды:

```powershell
python backend/scripts/ingest_knowledge.py --help
python backend/scripts/import_food_data.py --csv-dir backend/data/kaggle --dry-run
python backend/scripts/build_embeddings.py
```

Справочник содержит 2210 нормализованных продуктов. Комбинация перевода запроса,
multilingual embeddings и доменного ранжирования показала Recall@5 93% на
внутреннем наборе из 30 запросов.

## Безопасность

- GigaChat key и Supabase `service_role` существуют только на backend;
- TLS-проверка GigaChat всегда включена; при необходимости дополнительная цепочка
  доверия передаётся через `GIGACHAT_CA_BUNDLE_FILE`, а не отключением проверки;
- frontend передаёт Supabase access token в `Authorization: Bearer ...`;
- FastAPI получает `user_id` только из проверенного JWT;
- пользовательские запросы Supabase фильтруются по доверенному `user_id`;
- write-tools отделены от read-only tools и не получают автоматические retries;
- access tokens и значения секретов не выводятся в readiness или логи.

## Диагностика

### Docker API недоступен

Если отсутствует `dockerDesktopLinuxEngine`, запустите Docker Desktop и дождитесь
`Engine running`, затем выполните `docker version`.

### Порт 8001 занят

```powershell
Get-NetTCPConnection -LocalPort 8001 -State Listen
```

Остановите вручную запущенный Uvicorn перед публикацией порта Docker API.

### Chat возвращает 401

Проверьте, что `VITE_SUPABASE_URL` и `SUPABASE_URL` относятся к одному проекту,
затем очистите site data и войдите заново.

### GigaChat не отвечает

Проверьте Authorization key и доступные модели диагностическим скриптом:

```powershell
python backend/scripts/check_gigachat_api.py --insecure
```

`--insecure` допустим только для локальной диагностики TLS. Backend не должен
отключать проверку сертификатов в production.

## Структура проекта

```text
backend/app/
  agents/       LangGraph router, retriever и specialists
  api/          FastAPI endpoints
  auth/         Supabase JWT validation
  model_routing.py  GigaChat model-routing policy
  rag/          retrieval и ingestion contracts
  services/     jobs, conversations, tracing, Supabase
  tools/        read/write инструменты агента
  workers/      Celery application и tasks
supabase/
  migrations/   PostgreSQL, RLS, pgvector и agent traces
src/            React frontend
compose.yaml    Redis, FastAPI и Celery worker
```

## Лицензия

Добавьте условия лицензии проекта перед публичным распространением.
