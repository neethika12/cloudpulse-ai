# CloudPulse AI

AI-powered cloud cost monitoring platform. Connects to AWS billing data, visualizes spend, flags anomalies, and lets you chat with your spend through an LLM agent that combines SQL tool calling (for your numbers) with hybrid RAG over FinOps guides (for advice, with citations). Every answer is traced for tokens, cost and latency, and the RAG pipeline is measured by an eval harness gated in CI.

## Status

Feature-complete:

- FastAPI backend, PostgreSQL + SQLAlchemy models, Alembic migrations
- Mock AWS cost data generator (90 days across 6 services, with injected spend spikes)
- AI chat agent (OpenAI tool calling): read-only SQL tools over the user's own cost data for every figure, plus a `search_knowledge_base` tool for advice; answers stream token by token over SSE and the UI shows each tool call as it runs
- Hybrid RAG: 9 FinOps / AWS cost-optimization guides, heading-aware chunking with contextual headers, incremental embedding (`text-embedding-3-small`) into pgvector, vector + Postgres full-text retrieval fused with Reciprocal Rank Fusion, LLM reranking, and inline `[K1]` citations checked against what was actually retrieved
- LLM observability: every chat request is stored as a trace (tool steps, citations, tokens, cost, latency); an **AI usage** page shows totals, p50/p95 latency, tool usage and recent requests
- Evals: golden question sets, a retrieval ablation (keyword vs vector vs hybrid vs hybrid+rerank: hit@k, recall@k, MRR), and LLM-as-judge faithfulness/correctness scoring of end-to-end answers, with thresholds enforced in CI
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
                                       │  │ chat agent   │──┼──► OpenAI (chat, embeddings,
                                       │  │ retrieval    │  │    rerank, eval judge)
                                       │  └──────────────┘  │
                                       └─────────┬──────────┘
                                                  │
                                     ┌────────────▼────────────┐
                                     │ PostgreSQL + pgvector    │
                                     │ users / accounts / costs │
                                     │ anomalies / chat_traces  │
                                     │ knowledge_chunks (vector)│
                                     └──────────────────────────┘
```

How one chat question flows:

```
question ─► agent (gpt-4o, streamed) ─┬─► SQL tools ──────────► cost_records / anomalies (user's accounts only)
                                      └─► search_knowledge_base
                                            ├─ embed query ─► pgvector cosine (HNSW) ─┐
                                            └─ to_tsquery ──► Postgres FTS (GIN) ─────┴─► RRF ─► LLM rerank ─► top 5 as [K1..K5]
          ◄── SSE: tool_call · tool_result · token · done{answer, citations, usage} ──
          └─► chat_traces row: steps, citations, tokens, $ cost, latency
```

Everything runs as three Docker Compose services (`db`, `backend`, `frontend`); the external network calls are to OpenAI (chat and RAG), AWS (if you connect a real account) and Slack (if you configure a webhook).

## Key engineering decisions

A few choices worth being able to explain in an interview:

- **Tools for numbers, RAG for knowledge.** Cost data is small and structured, so it is queried with read-only SQL tools rather than embedded: answers about spend are exact and cover questions summaries could not (a spike on a given day, period comparisons). RAG is used where it fits: unstructured guidance. The agent decides per question which it needs, often both ("why did EC2 spike and what should I do?").
- **Hybrid retrieval, measured.** Vector search handles paraphrase ("my instances are too big" → rightsizing), full-text search handles exact jargon embeddings blur ("gp3", "NAT gateway", "Deep Archive"). Reciprocal Rank Fusion merges the two by rank, so cosine distance and `ts_rank` never need calibrating against each other, and a cheap LLM reranks the fused shortlist. `python -m evals.run` measures each stage separately, so the claim that hybrid+rerank beats either retriever alone is backed by numbers for this corpus.
- **Citations you can trust.** Retrieved passages are labelled `[K1]...[Kn]` per answer; the backend keeps only refs that a search actually returned, so a hallucinated `[K9]` never shows up as a source.
- **Contextual chunk headers + incremental indexing.** Chunks are split on `##` headings and paragraph boundaries and prefixed with `Doc title > Section`, so a passage still says what it is about when retrieved alone. Chunks are keyed by a hash of their text and the embedding model, so re-indexing only embeds what changed and switching embedding models re-embeds everything.
- **Every LLM call is metered.** One `UsageTracker` per request records tokens, latency and cost for the chat, embedding and rerank calls (streaming usage comes from `stream_options.include_usage`), and the request is saved as a `chat_traces` row. That is what the AI usage page and its p50/p95 latency are built from.
- **RAG has to beat a baseline.** The whole knowledge base is only about 15k tokens, small enough to paste into every prompt. The eval runs every answer question both ways, with RAG and with the full knowledge base in the prompt, and compares quality, tokens, cost and latency. RAG's case is lower cost per question and a corpus that can grow, not that it's the only option.
- **Evals that can fail CI.** Retrieval is scored at document level (hit@k, recall@k, MRR) against 30 standard questions plus 18 *hard* paraphrases that avoid the guides' wording (where keyword search is expected to struggle); answers are judged by an LLM for faithfulness *to the tool outputs and passages the agent actually saw* and for correctness against a reference. References for data questions are computed from the database at eval time, so they stay right whatever mock data is loaded. `--check` fails the build below `evals/thresholds.json`.
- **Chat is scoped and authenticated.** Chat spends API credits, so it requires login, and its SQL tools only see the user's own connected accounts (or the shared demo account), never another user's.
- **Anomaly detection as two filters, not one.** A raw `IsolationForest(contamination=0.1)` over-flags borderline-normal spend as anomalous. Its output is instead treated as a candidate shortlist, then a statistical `value > mean + 2*std` threshold decides what actually gets surfaced - fewer false positives than either approach alone.
- **Credentials encrypted at rest, validated before saving.** AWS secret access keys are Fernet-encrypted in the database; the backend never persists credentials AWS itself rejects; it always calls `sts.get_caller_identity()` first, before writing anything.
- **CI runs migrations against real Postgres+pgvector, not just SQLite.** Most tests run on SQLite for speed, where the embedding column falls back to JSON and retrieval to in-Python cosine/BM25 with the same interface. CI also runs `alembic upgrade head` against the real `pgvector/pgvector:pg16` image, and `test_retrieval_postgres.py` exercises the real pgvector + full-text retrievers there. OpenAI is replaced by a fake client in tests, so the suite needs no key.

## Tech stack

- Backend: FastAPI + Python
- Database: PostgreSQL + SQLAlchemy + Alembic
- AI: OpenAI API (streaming tool calling, `text-embedding-3-small`, LLM reranking, LLM-as-judge), pgvector (HNSW) + Postgres full-text search
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

Chat needs an OpenAI key, or an Azure OpenAI resource (set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and put your chat and embedding *deployment names* in `OPENAI_MODEL` and `OPENAI_EMBEDDING_MODEL`; see `.env.example`). For plain OpenAI: set `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`, default `gpt-4o`) in `backend/.env`, then restart the backend. The knowledge base indexes itself the first time the agent searches it (about 60 chunks, a fraction of a cent to embed), or re-index from the AI usage page. Everything else works without a key. If port 8000 is taken on your machine, put `BACKEND_PORT=8010` in a root `.env` and set `VITE_API_URL` in `frontend/.env` to match.

**Azure OpenAI.** Set `AZURE_OPENAI_ENDPOINT` (the portal's endpoint URL works as-is, including `.../openai/v1/responses`), `AZURE_OPENAI_API_KEY`, and put your deployment name in `OPENAI_MODEL`. Newer reasoning models (the gpt-5 family and later) don't support function tools on `/chat/completions`, so the agent automatically uses the Responses API for them (override with `LLM_CHAT_API=chat|responses`) and omits `temperature`. No embedding deployment? Set `OPENAI_EMBEDDING_MODEL=` (empty) and the knowledge base runs on keyword search only.

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

Apply database migrations (also enables the pgvector extension):

```bash
docker compose exec backend alembic upgrade head
```

Seed mock AWS cost data:

```bash
curl -X POST http://localhost:8000/api/costs/seed
```

Ask a question (chat requires a token from signup/login):

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/signup -H "Content-Type: application/json" \
  -d '{"email": "me@example.com", "password": "password123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8000/api/chat/ask \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"question": "Which service costs the most, and how could I reduce it?"}'

# Same thing as a Server-Sent Events stream
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"question": "How do I cut NAT gateway costs?"}'

# Compare retrievers for one query, without the chat model
curl -X POST http://localhost:8000/api/knowledge/search \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "gp3 vs gp2", "mode": "keyword", "rerank": false}'
```

Detect anomalies and optionally alert Slack:

```bash
curl -X POST http://localhost:8000/api/anomalies/detect
curl -X POST http://localhost:8000/api/anomalies/alert
```

`alert` requires `SLACK_WEBHOOK_URL` set in `backend/.env`. To get one: go to https://api.slack.com/apps → **Create New App** → **From scratch** → pick your workspace → under **Incoming Webhooks**, toggle it on → **Add New Webhook to Workspace** → choose a channel → copy the generated URL into `SLACK_WEBHOOK_URL`. Without it, the endpoint responds with `"sent": false` instead of failing.

On first visit, the UI shows a landing page, then a sign in / sign up screen - create an account to reach the dashboard. First-time users get a short guided tour. Auth gates the UI. The cost and anomaly API routes stay open since the demo data is shared; chat, the knowledge base and usage routes require a token, and chat only reads your own accounts' data (or the shared demo account until you sync a real one).

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
- `POST /api/chat/ask` — ask about cloud spend; body `{question, history}`; returns `{answer, citations, steps, usage}` (auth, needs `OPENAI_API_KEY`)
- `POST /api/chat/stream` — same, as Server-Sent Events: `tool_call`, `tool_result`, `token`, then `done` or `error` (auth)
- `GET /api/knowledge/status` — indexed chunks and guides (auth)
- `POST /api/knowledge/reindex` — re-read `backend/knowledge/*.md`, embed only new or changed chunks (auth)
- `POST /api/knowledge/search` — run retrieval alone; body `{query, mode: vector|keyword|hybrid, rerank, top_k}` (auth)
- `GET /api/llm/usage` — the current user's chat traces: totals, p50/p95 latency, tool usage, recent requests (auth)
- `POST /api/anomalies/detect` — run IsolationForest per service, store flagged days
- `GET /api/anomalies` — list currently stored anomalies
- `POST /api/anomalies/alert` — send detected anomalies to Slack (uses your per-user webhook from Settings if signed in, otherwise the shared `SLACK_WEBHOOK_URL`)

Everything above (seeding, asking questions, detecting anomalies, connecting AWS, Slack settings) can also be done from the UI.

## Tests

```bash
docker compose exec backend pytest -v
```

The suite uses a fake OpenAI client (`tests/fakes.py`), so it needs no API key and makes no network calls.

## Evals

Evals call the real models (OpenAI or Azure OpenAI, whichever is configured), so they need a key and cost money: about 20 agent runs, half of them with the full knowledge base in the prompt, plus rerank and judge calls.

```bash
docker compose exec backend python -m evals.run                    # retrieval ablation + RAG vs full-context answers
docker compose exec backend python -m evals.run --retrieval-only   # just the retriever comparison (cheapest)
docker compose exec backend python -m evals.run --no-baseline      # answers with RAG only
docker compose exec backend python -m evals.run --check            # exit 1 if below evals/thresholds.json
```

The report is written to `backend/evals/results/report.md` (plus `results.json`). It contains:
- a retrieval table for every configuration the current setup supports, on the standard and hard question sets. Vector and hybrid are marked skipped when no embedding model is set; the configuration the app actually uses is in bold, and the retrieval thresholds apply to it;
- the questions where that configuration missed;
- RAG vs full-context answers: faithfulness, correctness, citation rate, latency, tokens and cost, per question with the judge's reason, and the full answers for checking the judge by hand.

If the judge is the same model as the chat model, the report flags it as self-grading. Set `OPENAI_JUDGE_MODEL` to a different model for an independent judge. Golden sets live in `backend/evals/golden_*.jsonl`; add to them when you add a guide to `backend/knowledge/`.

## Monitoring

```bash
curl http://localhost:8000/health          # liveness
curl http://localhost:8000/health/ready    # readiness (checks the DB)
curl http://localhost:8000/metrics         # Prometheus metrics
docker compose logs -f backend             # structured request logs (method, path, status, latency)
```

## CI/CD

Every push and PR to `main` triggers a GitHub Actions workflow (`.github/workflows/ci.yml`) with four jobs:

- **backend-tests** — spins up a real `pgvector/pgvector:pg16` service container, runs `alembic upgrade head` against it, then runs the full pytest suite
- **rag-evals** — if the repository has an `OPENAI_API_KEY` secret, runs `python -m evals.run --check` against a real pgvector database and uploads the report as a build artifact; without the secret it skips, so forks still pass
- **frontend-build** — installs frontend deps and runs `tsc -b && vite build` (type-checks and builds for production)
- **docker-build** — builds both the backend and frontend Docker images to catch any Dockerfile breakage, gated on the two jobs above passing

Apart from the optional `OPENAI_API_KEY` secret for evals, no secrets or AWS credentials are needed.
