# CloudPulse AI

AI-powered cloud cost monitoring platform. Connects to AWS billing data, visualizes spend, and lets you chat with your infrastructure using an LLM-backed RAG pipeline.

## Status

Feature-complete:

- FastAPI backend, PostgreSQL + SQLAlchemy models, Alembic migrations
- Mock AWS cost data generator (90 days across 6 services, with injected spend spikes)
- RAG pipeline: LangChain orchestration, running entirely on local, open-source models (no API key or cloud AI account needed) - sentence-transformers for embeddings, flan-t5 for answer generation, pgvector for similarity search - so you can ask natural-language questions about your cloud spend
- Anomaly detection: scikit-learn IsolationForest per service, flags unusual daily spend, optional Slack alerts via incoming webhook
- React + TypeScript dashboard: sidebar layout, cost charts (by-service, trend), anomalies panel, and an AI chat UI, all talking to the FastAPI backend
- Auth: JWT-based signup/login/logout (bcrypt password hashing), gates access to the dashboard UI, with a guided first-time onboarding tour
- Real AWS integration: connect an IAM user's credentials (encrypted at rest) and pull real Cost Explorer data alongside the mock generator
- Per-user Slack webhook, configurable from a Settings page instead of only an env var
- CI/CD: GitHub Actions runs the backend test suite against a real Postgres+pgvector service container, type-checks and builds the frontend, and builds both Docker images on every push/PR to `main`
- Observability: structured request logging, a Kubernetes/ECS-style liveness + readiness split (`/health`, `/health/ready`), and Prometheus metrics at `/metrics`

Deployment (Docker Compose runs everything locally today; real AWS deployment - ECS, Terraform - is a natural next step, deliberately scoped out to avoid ongoing AWS spend on a portfolio project).

## Architecture

```
┌──────────────┐      REST/JSON       ┌──────────────────┐
│  React + TS  │ ───────────────────► │  FastAPI backend  │
│  (Vite,      │ ◄─────────────────── │                    │
│  Recharts)   │      JWT auth        │  ┌──────────────┐  │
└──────────────┘                      │  │ auth service │  │
                                       │  │ aws service  │──┼──► AWS STS / Cost Explorer
                                       │  │ anomaly svc  │──┼──► Slack incoming webhook
                                       │  │ rag service  │  │
                                       │  └──────────────┘  │
                                       └─────────┬──────────┘
                                                  │
                                     ┌────────────▼────────────┐
                                     │ PostgreSQL + pgvector    │
                                     │ users / accounts / costs │
                                     │ / anomalies / embeddings │
                                     └──────────────────────────┘
```

Everything runs as three Docker Compose services (`db`, `backend`, `frontend`); the only external network calls are to AWS (if you connect a real account) and Slack (if you configure a webhook) - the AI models are local, not API calls.

## Key engineering decisions

A few choices worth being able to explain in an interview:

- **Local-only AI stack, no API key.** Embeddings run through `sentence-transformers/all-MiniLM-L6-v2` and answer generation through `google/flan-t5-base`, both via Hugging Face `transformers`, orchestrated with LangChain. This was a deliberate pivot away from a hosted model (Azure OpenAI) to remove the cost/credential dependency entirely - anyone can clone the repo and run the full RAG pipeline with zero signup.
- **Grounding the LLM's answers against retrieved context.** `flan-t5-base` is small enough to sometimes drop the dollar figure from its answer even when it correctly identifies the service. Rather than fight this with prompt engineering alone, `rag_service.py` validates the generated answer against the retrieved context chunks and backfills the number if it's missing - a lightweight version of the "grounding" pattern used in production RAG systems.
- **Anomaly detection as two filters, not one.** A raw `IsolationForest(contamination=0.1)` over-flags borderline-normal spend as anomalous. Its output is instead treated as a candidate shortlist, then a statistical `value > mean + 2*std` threshold decides what actually gets surfaced - fewer false positives than either approach alone.
- **Credentials encrypted at rest, validated before saving.** AWS secret access keys are Fernet-encrypted in the database; the backend never persists credentials AWS itself rejects; it always calls `sts.get_caller_identity()` first, before writing anything.
- **CI runs migrations against real Postgres+pgvector, not just SQLite.** The test suite itself runs on SQLite for speed (pgvector's `Vector` column type isn't SQLite-compatible), but CI separately spins up the real `pgvector/pgvector:pg16` image and runs `alembic upgrade head` against it - the migration chain is verified against the actual database engine it will run on.

## Tech stack

- Backend: FastAPI + Python
- Database: PostgreSQL + SQLAlchemy + Alembic
- AI: LangChain, Hugging Face transformers (local embeddings + local chat model), pgvector for RAG retrieval
- ML: scikit-learn (IsolationForest anomaly detection)
- Cloud SDK: boto3 (AWS STS + Cost Explorer)
- Alerting: Slack incoming webhooks
- Frontend: React + TypeScript, Vite, Recharts
- Auth: JWT (python-jose) + bcrypt password hashing
- Secrets: Fernet (cryptography) encryption for stored AWS credentials
- CI/CD: GitHub Actions
- Observability: structured logging, Prometheus metrics (prometheus-fastapi-instrumentator)
- Infra (planned): AWS ECS, Terraform

## Running locally

Requires Docker Desktop.

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker compose up --build -d
```

Frontend available at `http://localhost:5173`.

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

On first visit, the UI shows a landing page, then a sign in / sign up screen - create an account to reach the dashboard. First-time users get a short guided tour. Auth gates the UI; the cost/anomaly/chat API routes themselves stay open since the underlying demo data is shared, not per-user - only the AWS-connect and Slack-webhook settings are tied to your account.

### Connecting a real AWS account

In the **Settings** tab, paste an IAM access key ID + secret access key and pick a region. The backend validates the credentials via STS before saving anything, encrypts the secret key at rest (Fernet), and "Sync real cost data" pulls the last 90 days from Cost Explorer, replacing the mock data for your account.

The IAM user needs at minimum:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ce:GetCostAndUsage", "sts:GetCallerIdentity"],
      "Resource": "*"
    }
  ]
}
```

Note: AWS Cost Explorer must be enabled on the account (one-time toggle in the Billing console), and it can take up to 24 hours after enabling before cost data is available.

## API endpoints

- `GET /health` — liveness check (process is up)
- `GET /health/ready` — readiness check (also confirms the database is reachable; returns 503 if not)
- `GET /metrics` — Prometheus-format metrics (request counts, latency histograms, status codes)
- `POST /api/auth/signup` — create an account, returns a JWT
- `POST /api/auth/login` — returns a JWT
- `GET /api/auth/me` — current user (requires `Authorization: Bearer <token>`)
- `PATCH /api/auth/me` — update profile: `full_name`, `slack_webhook_url`, `onboarding_completed`
- `GET /api/accounts` — list connected cloud accounts
- `GET /api/accounts/me` — the current user's connected AWS account, if any (requires auth)
- `POST /api/accounts/connect-aws` — validate + store AWS credentials (requires auth)
- `POST /api/accounts/sync` — pull real cost data from AWS Cost Explorer (requires auth)
- `POST /api/costs/seed` — seed mock cost data
- `GET /api/costs` — recent cost records
- `GET /api/costs/by-service` — total spend grouped by AWS service
- `GET /api/costs/trend` — total spend grouped by day
- `POST /api/chat/index` — embed current cost summary into pgvector
- `POST /api/chat/ask` — ask a natural-language question about cloud spend (RAG)
- `POST /api/anomalies/detect` — run IsolationForest per service, store flagged days
- `GET /api/anomalies` — list currently stored anomalies
- `POST /api/anomalies/alert` — send detected anomalies to Slack (uses your per-user webhook from Settings if signed in, otherwise the shared `SLACK_WEBHOOK_URL`)

Everything above (seeding, indexing, asking questions, detecting anomalies, connecting AWS, Slack settings) can also be done from the UI.

## Tests

```bash
docker compose exec backend pytest -v
```

## Monitoring

```bash
curl http://localhost:8000/health          # liveness
curl http://localhost:8000/health/ready    # readiness (checks the DB)
curl http://localhost:8000/metrics         # Prometheus metrics
docker compose logs -f backend             # structured request logs (method, path, status, latency)
```

## CI/CD

Every push and PR to `main` triggers a GitHub Actions workflow (`.github/workflows/ci.yml`) with three jobs:

- **backend-tests** — spins up a real `pgvector/pgvector:pg16` service container, runs `alembic upgrade head` against it, then runs the full pytest suite
- **frontend-build** — installs frontend deps and runs `tsc -b && vite build` (type-checks and builds for production)
- **docker-build** — builds both the backend and frontend Docker images to catch any Dockerfile breakage, gated on the two jobs above passing

No secrets or AWS credentials are needed - the pipeline is fully self-contained.
