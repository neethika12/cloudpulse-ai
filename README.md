# CloudPulse AI

AI-powered cloud cost monitoring platform. Connects to AWS billing data, visualizes spend, and lets you chat with your infrastructure using an LLM-backed RAG pipeline.

## Status

Weeks 1-3 of a 7-week build:

- FastAPI backend, PostgreSQL + SQLAlchemy models, Alembic migrations
- Mock AWS cost data generator (90 days across 6 services, with injected spend spikes for later anomaly detection work)
- RAG pipeline: LangChain orchestration, running entirely on local, open-source models (no API key or cloud AI account needed) - sentence-transformers for embeddings, flan-t5 for answer generation, pgvector for similarity search - so you can ask natural-language questions about your cloud spend

Frontend and deployment layers are still in progress.

## Tech stack

- Backend: FastAPI + Python
- Database: PostgreSQL + SQLAlchemy + Alembic
- AI: LangChain, Hugging Face transformers (local embeddings + local chat model), pgvector for RAG retrieval
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

## API endpoints

- `GET /health` — service health check
- `GET /api/accounts` — list connected cloud accounts
- `POST /api/costs/seed` — seed mock cost data
- `GET /api/costs` — recent cost records
- `GET /api/costs/by-service` — total spend grouped by AWS service
- `GET /api/costs/trend` — total spend grouped by day
- `POST /api/chat/index` — embed current cost summary into pgvector
- `POST /api/chat/ask` — ask a natural-language question about cloud spend (RAG)

## Tests

```bash
docker compose exec backend pytest -v
```
