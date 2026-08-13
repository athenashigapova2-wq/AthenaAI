# Redis и Celery workers

Chat работает через фоновую очередь:

1. `POST /api/v1/agent/chat` проверяет Supabase JWT и возвращает `202` с `job_id`.
2. Celery worker забирает задание из Redis, запускает LangGraph и сохраняет сообщения в Supabase.
3. Клиент опрашивает `GET /api/v1/agent/chat/jobs/{job_id}` до статуса `succeeded` или `failed`.

Записи статусов живут в Redis один час (`AGENT_JOB_TTL_SECONDS`). Статус доступен
только пользователю, чей `user_id` был извлечён из проверенного JWT. Задания агента
не повторяются автоматически: повтор state-changing tool call опаснее, чем явная
повторная отправка пользователем.

## Локальный запуск в Windows

Все команды ниже выполняются из корня репозитория в отдельных окнах PowerShell.

Сначала установите [Docker Desktop](https://www.docker.com/products/docker-desktop/),
затем зависимости проекта и запустите Redis:

```powershell
& ".\.venv\Scripts\Activate.ps1"
python -m pip install -r ".\backend\requirements.txt"
docker compose up -d redis
docker compose ps
```

Запустите API:

```powershell
& ".\.venv\Scripts\Activate.ps1"
python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8001
```

Запустите worker в другом окне. Потоковый pool поддерживается Windows и позволяет
обрабатывать до четырёх I/O-bound LLM-заданий одновременно:

```powershell
& ".\.venv\Scripts\Activate.ps1"
Set-Location ".\backend"
python -m celery -A app.workers.celery_app:celery_app worker --loglevel=INFO --pool=threads --concurrency=4
```

Затем запустите Vite как обычно на `5175`. Готовность Redis видна в
`http://127.0.0.1:8001/health/ready`: поле `redis` должно быть `ready`.

Остановка локального Redis:

```powershell
docker compose stop redis
```

## Production

API, Redis и worker должны быть отдельными процессами/сервисами. Всем экземплярам
API и workers задайте одинаковые `REDIS_URL` и `AGENT_JOB_QUEUE`. Redis не следует
публиковать в интернет; используйте приватную сеть и пароль/TLS, которые предоставляет
ваш managed Redis. Масштабируйте workers количеством процессов/контейнеров, сохраняя
одинаковое имя очереди.
