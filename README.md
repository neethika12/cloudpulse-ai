# CloudPulse AI

AI-powered cloud cost monitoring platform. Connects to AWS billing data, visualizes spend, and lets you chat with your infrastructure using an LLM-backed RAG pipeline.

## Status

Weeks 1-4 of a 7-week build:

- FastAPI backend, PostgreSQL + SQLAlchemy models, Alembic migrations
- Mock AWS cost data generator (90 days across 6 services, with injected spend spikes)
- RAG pipeline: LangChain orchestration, running entirely on local, open-source models (no API key or cloud AI account needed) - sentence-transformers for embeddings, flan-t5 for answer generation, pgvector for similarity search - so you can ask natural-language questions about your cloud spend
- Anomaly detection: scikit-learn IsolationForest per service, flags unusual daily spend, optional Slack alerts via incoming webhook

Frontend and deployment layers are still in progress.

## Tech stack

- Backend: FastAPI + Python
- Database: PostgreSQL + SQLAlchemy + Alembic
- AI: LangChain, Hugging Face transformers (local embeddings + local chat model), pgvector for RAG retrieval
- ML: scikit-learn (IsolationForest anomaly detection)
- Alerting: Slack incoming webhooks
- Frontend (planned): React + TypeScript
- Infra (planned): AWS ECS, Terraform, GitHub Actions

## Running locally

Requires Docker Desktop.

```bash
cp backend/.env.example backend/.env
docker compose up --build -d
```

No API key needed - both AI models run locally inside the backend container and download automatically from Hugging Face the first time they're used.

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

Apply database migrations (also enables the pgvector extension):

```bash
docker compose exec backend alembic upgrade head
```

Seed mock AWS cost data, then index it for chat:

```bash
curl -X POST http://localhost:8000/api/costs/seed
curl -X POST http://localhost:8000/api/chat/index
```

Ask a question:

```bash
curl -X POST http://localhost:8000/api/chat/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "which AWS service costs the most?"}'
```

Detect anomalies and optionally alert Slack:

```bash
curl -X POST http://localhost:8000/api/anomalies/detect
curl -X POST http://localhost:8000/api/anomalies/alert
```

`alert` requires `SLACK_WEBHOOK_URL` set in `backend/.env`. To get one: go to https://api.slack.com/apps → **Create New App** → **From scratch** → pick your workspace → under **Incoming Webhooks**, toggle it on → **Add New Webhook to Workspace** → choose a channel → copy the generated URL into `SLACK_WEBHOOK_URL`. Without it, the endpoint responds with `"sent": false` instead of failing.

## API endpoints

- `GET /health` — service health check
- `GET /api/accounts` — list connected cloud accounts
- `POST /api/costs/seed` — seed mock cost data
- `GET /api/costs` — recent cost records
- `GET /api/costs/by-service` — total spend grouped by AWS service
- `GET /api/costs/trend` — total spend grouped by day
- `POST /api/chat/index` — embed current cost summary into pgvector
- `POST /api/chat/ask` — ask a natural-language question about cloud spend (RAG)
- `POST /api/anomalies/detect` — run IsolationForest per service, store flagged days
- `GET /api/anomalies` — list currently stored anomalies
- `POST /api/anomalies/alert` — send detected anomalies to Slack (if configured)

## Tests

```bash
docker compose exec backend pytest -v
```
