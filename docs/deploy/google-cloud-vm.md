# Google Cloud VM Deployment

This guide deploys the feature-complete real-estate app on a Google Compute Engine VM with Docker Compose. The Compose stack runs PostgreSQL with pgvector, Redis, the backend API, the internal agent service, and the Next.js frontend.

## VM Target

- Ubuntu LTS
- 2 vCPU minimum
- 8 GB RAM recommended for BGE-M3 embeddings
- 50 GB disk minimum

## Install Runtime

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin git
sudo usermod -aG docker "$USER"
newgrp docker
docker --version
docker compose version
```

## Configure The App

```bash
git clone <repo-url> realestate-chatbot
cd realestate-chatbot
cp .env.example .env
```

Edit `.env` and set strong production values:

- `POSTGRES_PASSWORD`
- `JWT_SECRET_KEY`
- `AGENT_INTERNAL_KEY`
- `GEMINI_API_KEY`

Keep `CHATBOT_AGENT_SERVICE_ENABLED=false` for the first boot so the backend can be smoke-tested before routing chat requests to the internal agent service.

## Start Services

Start infrastructure first:

```bash
docker compose up -d --build postgres redis
```

Then start the application services:

```bash
docker compose up -d --build agent-service backend frontend
```

Check service state:

```bash
docker compose ps
docker compose logs --tail=100 backend
docker compose logs --tail=100 agent-service
```

## Smoke Tests

Backend health:

```bash
curl -f http://localhost:8000/api/v1/health
```

Internal agent health:

```bash
docker compose exec -T agent-service sh -lc \
  'curl -f -H "X-Internal-Agent-Key: $AGENT_INTERNAL_KEY" http://localhost:8100/internal/agent/health'
```

Frontend:

```bash
curl -f http://localhost:3000
```

The agent service is intended to be internal to Compose. Do not publish `8100:8100` in `docker-compose.yml`; run direct smoke tests from inside the `agent-service` container or another container on the Compose network.

## Enable Agent Routing

After backend and agent health checks pass, enable the internal agent service:

```bash
sed -i 's/^CHATBOT_AGENT_SERVICE_ENABLED=.*/CHATBOT_AGENT_SERVICE_ENABLED=true/' .env
docker compose up -d backend
```

Verify chat behavior through the frontend or backend chat endpoint after the backend restart completes.

## Backup PostgreSQL

Create a compressed database backup:

```bash
mkdir -p backups
docker compose exec -T postgres pg_dump \
  -U "${POSTGRES_USER:-admin}" \
  -d "${POSTGRES_DB:-realestate}" \
  | gzip > "backups/realestate-$(date +%Y%m%d-%H%M%S).sql.gz"
```
