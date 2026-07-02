# CloudPulse AI

AI-powered cloud cost monitoring platform. Connects to AWS billing data, visualizes spend, and lets you chat with your infrastructure using an LLM-backed RAG pipeline.

## Status

Weeks 1-5 of a 7-week build:

- FastAPI backend, PostgreSQL + SQLAlchemy models, Alembic migrations
- Mock AWS cost data generator (90 days across 6 services, with injected spend spikes)
- RAG pipeline: LangChain orchestration, running entirely on local, open-source models (no API key or cloud AI account needed) - sentence-transformers for embeddings, flan-t5 for answer generation, pgvector for similarity search - so you can ask natural-language questions about your cloud spend
- Anomaly detection: scikit-learn IsolationForest per service, flags unusual daily spend, optional Slack alerts via incoming webhook
- React + TypeScript dashboard: sidebar layout, cost charts (by-service, trend), anomalies panel, and an AI chat UI, all talking to the FastAPI backend
- Auth: JWT-based signup/login/logout (bcrypt password hashing), gates access to the dashboard UI, with a guided first-time onboarding tour
- Real AWS integration: connect an IAM user's credentials (encrypted at rest) and pull real Cost Explorer data alongside the mock generator
- Per-user Slack webhook, configurable from a Settings page instead of only an env var

Deployment (Docker Compose runs everything locally today; AWS/CI-CD is still planned).

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
- Infra (planned): AWS ECS, Terraform, GitHub Actions

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

- `GET /health` — service health check
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
