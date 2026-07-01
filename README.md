# CloudPulse AI

AI-powered cloud cost monitoring platform. Connects to AWS billing data, visualizes spend, and lets you chat with your infrastructure using an LLM-backed RAG pipeline.

## Status

Weeks 1-2 of a 7-week build: FastAPI backend, PostgreSQL + SQLAlchemy models, Alembic migrations, and a mock AWS cost data generator (90 days across 6 services, with injected spend spikes for later anomaly detection work). AI, frontend, and deployment layers are in progress.

## Tech stack

- Backend: FastAPI + Python
- Database: PostgreSQL + SQLAlchemy + Alembic
- AI (planned): LangChain + OpenAI, RAG with pgvector
- Frontend (planned): React + TypeScript
- Infra (planned): Docker, AWS ECS, Terraform, GitHub Actions

## Running locally

Requires Docker Desktop.

```bash
cp backend/.env.example backend/.env
docker compose up --build -d
```

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

Apply database migrations:

```bash
docker compose exec backend alembic upgrade head
```

Seed mock AWS cost data:

```bash
curl -X POST http://localhost:8000/api/costs/seed
```

## API endpoints

- `GET /health` — service health check
- `GET /api/accounts` — list connected cloud accounts
- `POST /api/costs/seed` — seed mock cost data
- `GET /api/costs` — recent cost records
- `GET /api/costs/by-service` — total spend grouped by AWS service
- `GET /api/costs/trend` — total spend grouped by day

## Tests

```bash
docker compose exec backend pytest -v
```
