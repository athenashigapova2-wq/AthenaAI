# Permanent backend deployment

This deployment keeps the existing Athena architecture: one FastAPI container,
one Celery worker, and one private Redis instance. Caddy is the only
Internet-facing container and terminates HTTPS automatically.

## Server requirements

- A Linux VPS with a public IPv4 address.
- At least 4 GB RAM and 2 vCPU; 8 GB RAM is safer while building the CPU image.
- Docker Engine with the Compose plugin.
- TCP ports 22, 80, and 443 allowed by the server firewall.
- A DNS record such as `api.aminashigapova.ru` pointing to the VPS.

Redis and FastAPI are not published directly on the host. Only Caddy publishes
ports 80 and 443.

## First deployment

```bash
git clone https://github.com/athenashigapova2-wq/AthenaAI.git
cd AthenaAI
cp deploy/production/backend.env.example deploy/production/backend.env
chmod 600 deploy/production/backend.env
```

Fill the empty secrets and replace the example CORS origins in
`deploy/production/backend.env`. Do not put frontend `VITE_*` variables in this
file.

Set the API hostname and validate the fully rendered Compose configuration:

```bash
export ATHENA_API_DOMAIN=api.aminashigapova.ru
docker compose --env-file deploy/production/backend.env \
  -f compose.production.yaml config --quiet
```

Build and start the services:

```bash
docker compose --env-file deploy/production/backend.env \
  -f compose.production.yaml up -d --build
docker compose -f compose.production.yaml ps
curl --fail https://api.aminashigapova.ru/health/ready
```

The readiness response must report `status=ready`, `redis=ready`,
`llm_provider=gigachat`, and `agent_infrastructure_test_mode=false`.

## Updates

```bash
git pull --ff-only origin main
export ATHENA_API_DOMAIN=api.aminashigapova.ru
docker compose --env-file deploy/production/backend.env \
  -f compose.production.yaml up -d --build --remove-orphans
```

After the permanent endpoint is healthy, set `VITE_AGENT_API_URL` to its HTTPS
origin in Cloudflare and Vercel. Rebuild the signed Android release against the
same origin. Keep the old ngrok endpoint only for local troubleshooting.

## Backup and recovery

Redis uses an append-only file in the named volume `redis-data`. Redis contains
job state and queue data, not the authoritative user records stored in
Supabase. Before server maintenance, stop API and worker, then archive the
volume if preserving in-flight jobs is important.

Secrets and the release keystore require independent encrypted backups. They
are not included in Docker volumes or Git.
