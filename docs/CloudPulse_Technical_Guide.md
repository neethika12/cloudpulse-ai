# CloudPulse AI: Project and Technical Guide

An AI assistant for understanding and reducing your AWS bill. This document explains what the project does at a high level, then every major technical piece: the stack, the data, the LLM layer, the agent, and the RAG pipeline in depth (chunking, embeddings, vector storage and scaling, hybrid retrieval, reranking, citations, evaluation).

> **Snapshot note.** This describes the code as of 2026-11-20. Where behavior depends on configuration (for example, vector search needs an embedding model), the text says so. The current local setup uses an Azure OpenAI chat deployment (`gpt-6.1-sol`) and **no embedding deployment**, so retrieval currently runs as keyword search plus LLM reranking.

---

## Contents

1. [The best points (summary)](#1-the-best-points-summary)
2. [What the product does](#2-what-the-product-does)
3. [Architecture](#3-architecture)
4. [Tech stack](#4-tech-stack)
5. [Data model](#5-data-model)
6. [Cost data: demo data and real AWS](#6-cost-data-demo-data-and-real-aws)
7. [Anomaly detection](#7-anomaly-detection)
8. [The LLM layer](#8-the-llm-layer)
9. [The chat agent](#9-the-chat-agent)
10. [RAG in depth](#10-rag-in-depth)
11. [Vector storage and scaling](#11-vector-storage-and-scaling)
12. [Evaluation](#12-evaluation)
13. [Security](#13-security)
14. [Observability and operations](#14-observability-and-operations)
15. [Frontend](#15-frontend)
16. [API reference](#16-api-reference)
17. [Configuration reference](#17-configuration-reference)
18. [Testing and CI](#18-testing-and-ci)
19. [Known limitations and roadmap](#19-known-limitations-and-roadmap)
20. [Glossary](#20-glossary)
21. [Interview talking points](#21-interview-talking-points)

---

## 1. The best points (summary)

- **Grounded numbers.** The model never invents a figure about your spend. Every dollar amount comes from a SQL tool the model must call. This is the core trust pattern for AI over financial data.
- **Real RAG for advice.** FinOps advice comes from a knowledge base (9 guides, 57 chunks) retrieved with a search tool, ranked by an LLM reranker, and cited as `[K1]`, `[K2]` in the answer. Only refs that were actually retrieved can appear as citations.
- **Hybrid retrieval architecture.** Keyword search (Postgres full-text) and vector search (pgvector, HNSW) are merged with Reciprocal Rank Fusion, then reranked. Vector search switches on when an embedding model is configured.
- **Measured, not claimed.** An eval harness scores retrieval (hit@k, recall@k, MRR) and answers (faithfulness, correctness, citation rate), and compares RAG against a "stuff everything in the prompt" baseline.
- **Agentic loop with streaming.** The model decides which tools to call, up to 6 rounds. Tool calls, results, and answer tokens stream to the browser over Server-Sent Events, so users see the agent working.
- **Provider-flexible.** Works with OpenAI or Azure OpenAI, including the Azure v1 endpoint, and with newer reasoning models that require the Responses API.
- **Per-request accounting.** Every chat is traced: tokens, cost, latency, tools used, citations. A usage page and a per-user rate limit sit on top of that.
- **Production habits.** JWT auth, bcrypt, Fernet-encrypted AWS secrets, Alembic migrations, health and readiness probes, Prometheus metrics, Docker Compose, GitHub Actions CI against real Postgres.

---

## 2. What the product does

**One-line description:** a web app that shows where your AWS money goes, flags unusual spikes, and lets you ask questions in plain English.

**The problem.** AWS bills are hard to read. Cost Explorer gives charts and filters, but you must already know what to look for. Teams often discover a spike at month end, then spend hours digging.

**What CloudPulse offers**

| Feature | What the user gets |
|---|---|
| Dashboard | Total spend, top service, average daily spend, spend by service, daily trend |
| Anomaly detection | Days where a service's spend is unusually high, with optional Slack alerts |
| AI chat | Plain-English questions answered with exact numbers from the user's data plus cited FinOps advice |
| AWS connection | Paste an IAM key; the app pulls 90 days of real cost data from Cost Explorer |
| AI usage page | Requests, tokens, latency percentiles, cost, tools used, how many answers had citations |
| Accounts | Sign up, log in, guided first-time tour, per-user Slack webhook |

**Who it is for.** Small teams without a dedicated FinOps person, engineering managers and founders who want quick answers, and learners who want to explore cloud cost behavior with demo data. It is not aimed at large enterprises that already use mature tools.

**Main aim of the project.** It is a portfolio project: it demonstrates full-stack engineering, applied LLM agents, RAG with measured quality, classical ML (anomaly detection), and production practices.

---

## 3. Architecture

```
 Browser (React + TypeScript, Vite, Recharts)
        |  REST/JSON + Server-Sent Events (SSE), JWT bearer token
        v
 FastAPI backend (Python 3.11)
   +-- auth        signup / login / me (JWT, bcrypt)
   +-- costs       seed demo data, totals, trend
   +-- accounts    connect AWS (STS check), sync (Cost Explorer)
   +-- anomalies   IsolationForest + std-dev filter, Slack alert
   +-- chat        /ask and /stream -> chat agent
   +-- knowledge   status, reindex, search (RAG tooling)
   +-- usage       /api/llm/usage (tokens, cost, latency)
        |                 |                    |               |
        v                 v                    v               v
 PostgreSQL 16     Azure OpenAI /         AWS STS +        Slack incoming
 + pgvector        OpenAI                 Cost Explorer    webhook
 (users, accounts, (chat, rerank,         (boto3)
 costs, anomalies, [embeddings])
 knowledge_chunks,
 chat_traces)
```

**Runtime.** Three Docker Compose services: `db` (image `pgvector/pgvector:pg16`), `backend` (python:3.11-slim, uvicorn with `--reload`, source bind-mounted), `frontend` (Node, Vite dev server, with `usePolling` enabled because file events do not cross the Docker-on-Mac bind mount). The backend host port is configurable with `BACKEND_PORT` (default 8000; 8010 in this local setup).

**One chat request, end to end**

```
1. Browser POSTs {question, history} to /api/chat/stream with the JWT.
2. Backend checks login and the per-user hourly rate limit.
3. Agent builds the prompt: system prompt + trimmed history + question.
4. Model turn (streamed). The model either answers or asks for tools.
5. Tool calls run on the server (SQL over cost data, or knowledge search).
   Results go back to the model. Repeat up to 6 rounds.
6. Final answer streams out; citations are extracted; a ChatTrace row is saved.
```

---

## 4. Tech stack

| Layer | Technology | Role |
|---|---|---|
| Frontend | React 18, TypeScript, Vite 5, Recharts 2, lucide-react | UI, charts, streaming chat |
| Backend | FastAPI, Pydantic v2, pydantic-settings, uvicorn | HTTP API, validation, configuration |
| Database | PostgreSQL 16 + pgvector, SQLAlchemy 2, Alembic | Storage, migrations, vector and full-text indexes |
| LLM | `openai` Python SDK 1.x (OpenAI or Azure OpenAI) | Chat, reranking, judging, embeddings |
| ML | scikit-learn IsolationForest, NumPy | Anomaly detection |
| AWS | boto3 | STS identity check, Cost Explorer |
| Auth | python-jose (JWT HS256), bcrypt | Login |
| Crypto | cryptography (Fernet) | Encrypt stored AWS secret keys |
| Metrics | prometheus-fastapi-instrumentator | `/metrics` |
| Tests | pytest, httpx TestClient, a fake OpenAI client | 45 tests |
| CI/CD | GitHub Actions | Tests, evals, frontend build, Docker build |
| Containers | Docker, Docker Compose | Local runtime |

The project originally used local Hugging Face models (flan-t5, sentence-transformers) with LangChain. Those were replaced with the tool-calling agent described below.

---

## 5. Data model

| Table | Purpose | Key columns |
|---|---|---|
| `users` | Accounts | email (unique), hashed_password, full_name, slack_webhook_url, onboarding_completed |
| `accounts` | A cloud account | user_id (nullable: null means shared demo account), aws_account_id (unique), is_connected, aws_access_key_id, aws_secret_access_key_encrypted, aws_region |
| `cost_records` | One row per account, service, day | account_id, service (indexed), date (indexed), amount_usd |
| `anomalies` | Flagged spike days | account_id, service, date, amount_usd, detected_at |
| `knowledge_chunks` | RAG passages | source, title, section, chunk_index, content, content_hash (unique), embedding `vector(1536)`, created_at |
| `chat_traces` | One row per chat request | user_id, question, answer, status, model, steps (JSON), citations (JSON), llm_calls, prompt_tokens, completion_tokens, cost_usd, latency_ms, created_at |

**Indexes on `knowledge_chunks`**

- `ix_knowledge_chunks_source`: B-tree on `source`.
- `ix_knowledge_chunks_embedding`: `HNSW (embedding vector_cosine_ops)`, the approximate nearest-neighbor index for the vector retriever.
- `ix_knowledge_chunks_fts`: `GIN (to_tsvector('english', content))`, the full-text index for the keyword retriever. The query must use the same expression to use the index.

**Migrations (Alembic, in order):** accounts and cost_records; pgvector extension and early embeddings table; switch to 384-dim local vectors; anomalies; users; AWS-connect and Slack fields; knowledge_chunks and chat_traces (drops the old `cost_embeddings` table). In tests the vector column falls back to JSON on SQLite.

---

## 6. Cost data: demo data and real AWS

### 6.1 Demo data (the "testing dataset")

Generated on demand by `POST /api/costs/seed` (button on the dashboard).

- 90 days of daily records for 6 services = 540 records.
- Each service has a random daily range: EC2 $40-90, RDS $20-45, S3 $5-15, CloudFront $3-10, Lambda $2-8, VPC $1-4.
- Two planted spikes, 12 and 45 days ago: EC2 and RDS are multiplied by 3-5x, so the anomaly detector has something to find.
- Stored under a shared demo account (`aws_account_id = 123456789012`, `user_id` null).
- Re-seeding replaces the old demo records and anomalies instead of duplicating them.
- Amounts are random each time, so exact dollars change; the structure does not.

### 6.2 Real AWS data

1. **Connect** (`POST /api/accounts/connect-aws`): the user submits access key ID, secret, and region. The backend first calls `sts.get_caller_identity()`. If AWS rejects the credentials, nothing is saved. On success it stores the AWS account ID, the access key ID, and the secret **encrypted with Fernet**.
2. **Sync** (`POST /api/accounts/sync`): decrypts the secret, calls Cost Explorer `get_cost_and_usage` with `Granularity=DAILY`, `Metrics=[UnblendedCost]`, `GroupBy=SERVICE`, for the last 90 days. Zero-amount rows are skipped. The account's existing cost records are replaced.
3. Minimum IAM permissions: `ce:GetCostAndUsage`, `sts:GetCallerIdentity`. Cost Explorer must be enabled on the AWS account (data can take up to 24 hours after enabling).

**Which data the chat sees.** `accessible_account_ids()`: the user's own connected accounts if they hold cost data; otherwise the shared demo accounts. Never another user's account.

> This real-AWS path is implemented and unit-tested with mocks, but has not been exercised against a live AWS account in this project.

---

## 7. Anomaly detection

Runs per service, over that service's daily amounts (`POST /api/anomalies/detect`).

1. Require at least 10 records for the service.
2. Fit `IsolationForest(contamination=0.1, random_state=42)` on the daily amounts. It labels the most unusual ~10% of days as candidates (`-1`).
3. **Second filter:** keep a candidate only if `amount > mean + 2 * std` for that service.
4. Replace the stored anomalies with the result.

**Why two filters.** An IsolationForest with fixed contamination always flags about 10% of points, even when nothing is truly abnormal, and it cannot return zero anomalies. Treating it as a shortlist and then requiring a statistical extreme removes borderline-normal days.

**Why per service.** Services have very different normal ranges (EC2 vs VPC). Pooling them would flag "expensive services", not "unusual days".

**Slack alerts.** `POST /api/anomalies/alert` sends the stored anomalies to a Slack incoming webhook: the signed-in user's webhook from Settings if set, otherwise the `SLACK_WEBHOOK_URL` environment value. With no webhook it responds `sent: false` instead of failing.

---

## 8. The LLM layer

All model calls go through one module, `app/services/llm.py`. It does five jobs.

### 8.1 Provider selection

- **OpenAI:** `OpenAI(api_key=OPENAI_API_KEY)`.
- **Azure OpenAI (v1 endpoint):** if `AZURE_OPENAI_ENDPOINT` contains `/openai/v1` (the portal shows `.../openai/v1/responses`), the code normalizes it to `.../openai/v1/` and uses the plain `OpenAI` client with `base_url` set to it. The `model` argument of every call is the **deployment name**.
- **Azure OpenAI (classic):** a plain resource endpoint uses `AzureOpenAI` with `api_version` (default `2024-10-21`).
- If nothing is configured, chat endpoints return HTTP 503 with a clear message; the rest of the app keeps working.

### 8.2 Which API is called

Newer reasoning models (for example `gpt-6.1-sol` here) reject function tools on `/chat/completions`. Azure's error says to use `/responses`, and setting `reasoning_effort` to `none` is rejected as unsupported for that model. So:

- `LLM_CHAT_API=auto` (default): use **Chat Completions** for model names starting with `gpt-4` or `gpt-3.5`, and the **Responses API** for everything else. It can be forced with `chat` or `responses`.
- The agent keeps its history in chat-completions format. For the Responses API, `_to_responses_input()` converts it: system messages become `instructions`; user and assistant messages stay as messages; assistant tool calls become `function_call` items; tool results become `function_call_output` items. Tool definitions are flattened to the Responses shape. Requests use `store=False`.

### 8.3 Streaming

`stream_chat()` yields text deltas as they arrive and fills a `StreamedTurn` (content plus tool calls).

- Chat Completions: reassembles tool-call fragments by index; usage comes from the final chunk (`stream_options.include_usage`).
- Responses: listens for `response.output_text.delta` (text), `response.output_item.done` with a `function_call` item (complete tool call), and `response.completed` (token usage). A `failed`, `incomplete`, or `error` event raises.

### 8.4 Sampling parameters

`temperature` is only sent to `gpt-4*` and `gpt-3.5*` models (0.2 for chat, 0 for JSON calls), because newer reasoning models reject a custom temperature. Override with `LLM_SEND_TEMPERATURE=true|false`.

### 8.5 Usage and cost accounting

A `UsageTracker` is created per request. Every call records `kind` (chat, embedding, rerank, judge), model, prompt tokens, completion tokens, latency, and cost. Cost uses a USD-per-million-token table with **longest-prefix matching** (so `gpt-4o-2024-08-06` prices as `gpt-4o` and `gpt-4o-mini` is not priced as `gpt-4o`), merged with `OPENAI_PRICING_OVERRIDES` (JSON, for custom Azure deployment names). Unknown models are tracked with cost `None`, and the usage page counts them as "unpriced". If any call in a request is unpriced, that request's total cost is `None` rather than a misleading partial sum.

### 8.6 Other calls

- `complete_json()`: single non-streaming call in JSON mode (`response_format={"type": "json_object"}`), used for reranking and eval judging.
- `embed()`: batches of up to 100 texts; passes `dimensions=1536` unless `EMBEDDING_SUPPORTS_DIMENSIONS=false` (needed for `text-embedding-ada-002`, which always returns 1536 and rejects the argument).
- Reranking and judging models default to the chat model on Azure (where `gpt-4o-mini` may not be deployed) and to `gpt-4o-mini` on OpenAI.

---

## 9. The chat agent

`app/services/chat_agent.py`. It is an LLM agent: the model decides which tools to call; the server executes them and feeds the results back.

### 9.1 Two kinds of knowledge, two mechanisms

| Question type | Example | Mechanism |
|---|---|---|
| About the user's own spend | "Which service costs the most?" | **SQL tools** (not RAG) |
| About how to fix or optimize | "How do I cut NAT gateway costs?" | **RAG**: `search_knowledge_base` |
| Mixed | "Why did EC2 spike and what should I check?" | Both |

### 9.2 Tools

| Tool | What it does |
|---|---|
| `get_cost_summary(start_date?, end_date?)` | Total per service in the range, ranked, plus grand total |
| `get_daily_costs(service?, start_date?, end_date?)` | Daily totals for one service or all (last 120 days returned) |
| `compare_periods(period_a_*, period_b_*)` | Per-service change in dollars and percent between two ranges, sorted by absolute change |
| `get_anomalies()` | Stored spike days |
| `search_knowledge_base(query)` | Hybrid retrieval over the FinOps guides; returns passages labeled with refs |

All SQL tools are read-only and filtered by `account_id IN (accessible accounts)`, so one user cannot read another's data. Tool errors are returned to the model as `{"error": ...}` instead of crashing the request.

### 9.3 The system prompt (what it enforces)

- States today's date, currency, and the data range available to this user.
- Says to use cost tools for any number about the user's spend and never to guess or invent figures.
- Says to use the knowledge search for "how", "why", and "what should I do" questions, and before recommending a fix.
- **Citation rules:** cite a passage with its ref right after the sentence, like `[K2]`; cite only refs a search actually returned; do not cite the cost tools; say that guide prices are general list prices, not the user's bill.
- Style: concise, exact dollar amounts; for spikes, check daily costs and anomalies first, then explain and suggest one or two next steps; say plainly when the data does not contain the answer.

### 9.4 The loop

```
messages = [system prompt, trimmed history, user question]
for round in 1..6:
    stream one model turn  -> emit "token" events for text
    if no tool calls: answer = text; stop
    append the assistant tool calls to messages
    for each tool call:
        emit "tool_call"; run the tool; emit "tool_result" (short summary)
        append the tool result to messages
if the loop ends without an answer: return a "could not finish" message
emit "done" with answer, citations, sources, steps, usage
always: save a ChatTrace row (even on error or early client disconnect)
```

- **History trimming:** the most recent messages that fit both limits: 12 messages and 24,000 characters (about 6k tokens).
- **Events** (SSE): `tool_call`, `tool_result`, `token`, then `done` or `error`. The full tool result stays on the server; the browser receives only a short summary per tool step.
- **Non-streaming:** `POST /api/chat/ask` runs the same loop and returns the `done` payload.
- **Rate limit:** `CHAT_REQUESTS_PER_HOUR` (default 60) per user, counted from `chat_traces`; exceeding it returns HTTP 429.
- **Errors:** provider failures become a generic 502 or an `error` event; details go to the server log.

### 9.5 Knowledge modes (used by evals)

`knowledge_mode="rag"` (default): the model calls the search tool. `knowledge_mode="full_context"`: the search tool is removed and **all** 57 chunks are placed in the system prompt, labeled `[K1]`... This is the baseline RAG must beat.

---

## 10. RAG in depth

### 10.1 The corpus

Nine markdown guides in `backend/knowledge/`: cost-anomaly runbook, EC2 rightsizing, Lambda and serverless, networking and data transfer, RDS and Aurora, S3 storage, Savings Plans and Reserved Instances, EC2 Spot, tagging/budgets/FinOps practice. Result after chunking: **57 chunks**, average 430 characters, maximum 1,059 characters. Chunk counts per guide: 5 to 7.

### 10.2 Ingestion pipeline

```
guides (*.md)
   -> split into sections on "##" headings
   -> pack paragraphs into chunks of at most 1,200 characters
      (an oversized single paragraph is hard-split into 1,200-char windows
       with 200-char overlap, breaking on spaces)
   -> prefix each chunk with a contextual header: "<Doc title> > <Section>"
   -> hash = sha256(embedding_model + "\n" + chunk text)
   -> compare with stored hashes:
        new hash   -> embed (if embeddings enabled) and insert
        stale hash -> delete
        same hash  -> leave untouched
   -> store in knowledge_chunks (GIN full-text index + HNSW vector index)
```

Design points:

- **Heading-aware chunking** keeps each chunk about one idea.
- **Contextual header**: a passage such as "Delete them after 7 days" still says what it is about when retrieved on its own, which helps both keyword matching and the model reading it.
- **Incremental, idempotent ingestion**: re-running only embeds new or edited chunks and removes stale ones. Because the embedding model name is part of the hash, switching models re-embeds everything.
- **Lazy first-use indexing**: `ensure_indexed()` builds the index the first time the agent searches, so a fresh install needs no manual step. A concurrent-request race is handled by catching `IntegrityError` (the other request's insert wins).
- **Manual control:** `POST /api/knowledge/reindex` and `GET /api/knowledge/status`.
- **Keyword-only mode:** when `OPENAI_EMBEDDING_MODEL` is empty, chunks are stored with a placeholder zero vector (the column is NOT NULL) and vector search is skipped.

### 10.3 Query-time pipeline

```
user question
   -> model writes a focused search query (tool call, max 300 chars)
   -> [Keyword retriever]  Postgres full-text, top 20
   -> [Vector retriever]   pgvector cosine, top 20      (only if embeddings enabled)
   -> Reciprocal Rank Fusion merges the lists
   -> LLM reranker reorders a shortlist of 10
   -> top 5 passages returned to the agent, labeled [K1]..[K5]
   -> model writes the answer and cites refs
```

**Keyword retriever.** The query is lowercased and tokenized with `[a-z0-9]+`; stopwords and single characters are removed. Postgres builds `to_tsquery('english', 't1 | t2 | ...')`: terms are OR-ed because `plainto_tsquery` and `websearch_to_tsquery` AND them, which returns nothing for most natural-language questions. Results are ordered by `ts_rank_cd`. Tokens contain only `[a-z0-9]`, so building the query string is injection-safe. On SQLite (tests) the same interface uses an in-Python BM25 (k1 = 1.5, b = 0.75).

**Vector retriever.** The query is embedded with the same model and dimensions; Postgres orders by `embedding <=> query_vector` (cosine distance) using the HNSW index. On SQLite (tests) it computes cosine similarity in Python.

**Why both.** Vector search catches paraphrases ("shrink my instance bill" ~ "rightsizing"). Keyword search catches exact terms embeddings blur together ("NAT gateway", "gp3", "Deep Archive").

**Reciprocal Rank Fusion (RRF).** Each retriever returns a ranked list. A passage's fused score is the sum over retrievers of `1 / (60 + rank)`. Only ranks are used, so the two incomparable scores (cosine distance vs `ts_rank`) never need calibration. The constant 60 is the standard value from the original RRF paper (Cormack et al., 2009).

**LLM reranker.** The top fused candidates (shortlist of `max(top_k * 2, 10)` = 10) are shown to the model, each truncated to 700 characters, with the question. The model returns JSON `{"ranking": [passage numbers]}`, most useful first, omitting irrelevant ones. Anything the reranker skipped is appended at the end so an over-strict reranker cannot empty the results. If reranking fails, the fused order is used.

**Defaults:** `RAG_CANDIDATES=20` per retriever, `RAG_TOP_K=5`, `RAG_RERANK=true`.

### 10.4 Citations

- Passages are numbered `K1`, `K2`, ... **across all searches in one answer**, with duplicates mapped to the same ref.
- The model must cite refs inline. After the answer is complete, the server extracts every `[K#]` with a regex and keeps only refs that were actually returned by a search (in first-appearance order). Invented refs are dropped.
- The UI renders known refs as clickable badges and shows a Sources panel (guide title, section, snippet).
- Citation rate is an eval metric.

### 10.5 Current state of vector search

With no embedding model configured, the app runs **keyword search + LLM rerank**. The vector retriever, hybrid fusion, and the HNSW index are implemented and tested, and switch on by setting `OPENAI_EMBEDDING_MODEL` to an embedding deployment (no code change). The eval harness marks vector and hybrid configurations as "skipped" until then.

### 10.6 Retrieval modes available

`search(db, query, mode, use_rerank, top_k)` supports `vector`, `keyword`, and `hybrid`, each with or without rerank. `POST /api/knowledge/search` exposes this for side-by-side comparison without the chat model.

---

## 11. Vector storage and scaling

**What an embedding is.** A list of floating-point numbers (a vector) that represents the meaning of a piece of text. Texts with similar meaning have vectors that point in similar directions; similarity is measured with cosine distance.

**How it is stored here**

- Column type `vector(1536)` (pgvector), matching `text-embedding-3-small`'s default 1536 dimensions. The dimension is set by `EMBEDDING_DIMENSIONS` and must match the migration.
- Distance operator `<=>` (cosine) with the operator class `vector_cosine_ops`.
- Index: **HNSW** (Hierarchical Navigable Small World), an approximate nearest-neighbor graph. It trades a little recall for much faster search than scanning every row. The index uses pgvector's defaults (`m = 16`, `ef_construction = 64`; query-time `hnsw.ef_search = 40`).

**Size estimates** (float32 = 4 bytes per dimension, so 1536 x 4 = 6,144 bytes, about 6 KB per vector, before row and index overhead)

| Chunks | Raw vector storage (approx.) |
|---|---|
| 57 (today) | about 0.35 MB |
| 10,000 | about 60 MB |
| 1,000,000 | about 6 GB (plus index) |

**At today's size** an exact scan would be just as fast; the HNSW index is there to demonstrate the production pattern and to keep latency flat as the corpus grows.

**Scaling levers**

- **Dimensions:** `text-embedding-3` models can return shorter vectors (for example 256 or 512) via the `dimensions` argument, cutting storage and speeding search, at a small quality cost. The column size and `EMBEDDING_DIMENSIONS` would change together and require a migration plus re-embedding.
- **Batching:** embeddings are requested in batches of up to 100 texts.
- **Incremental ingestion:** only new or changed chunks are embedded, so adding documents costs little.
- **Filtering and tenancy:** for user-uploaded documents, add a `user_id` or `document_id` column and filter inside both retrievers (a roadmap item).
- **Query-embedding cache:** repeated queries need not be re-embedded.
- **Index tuning:** raise `hnsw.ef_search` for higher recall, `m` and `ef_construction` for a better graph.
- **Beyond pgvector:** pgvector with HNSW is comfortable into the millions of vectors on one Postgres; a dedicated vector database is only warranted at much larger scale or special needs.

**Full-text side.** The GIN index over `to_tsvector('english', content)` gives fast keyword search; the same expression is used at query time so the index is used.

---

## 12. Evaluation

Code in `backend/evals/`. Run with `python -m evals.run` (add `--check` to enforce thresholds).

### 12.1 Datasets

| File | Size | Purpose |
|---|---|---|
| `golden_retrieval.jsonl` | 30 questions | Each lists which guide(s) should be retrieved |
| `golden_retrieval_hard.jsonl` | 18 questions | Paraphrases that avoid the guides' wording |
| `golden_answers.jsonl` | 10 questions | Knowledge, data, and mixed questions with reference answers |

### 12.2 Metrics

- **Retrieval (document level; a retrieved chunk counts if it comes from a relevant guide):** hit@1, hit@k, recall@k, MRR (mean reciprocal rank). k = 5.
- **Answers (LLM as judge):** *faithfulness* (are claims supported by the context the agent saw), *correctness* (matches the reference), *citation rate* (answers that cite when they should).
- **Cost and speed:** average latency, tokens, cost per answer.

### 12.3 Thresholds (`thresholds.json`)

Retrieval hit@5 >= 0.9 and MRR >= 0.7; answers faithfulness >= 0.8, correctness >= 0.75, citation rate >= 0.8. CI runs evals with `--check` when an API-key secret exists.

### 12.4 Latest results (2026-11-20; Azure `gpt-6.1-sol`; keyword-only retrieval)

| Configuration | Question set | hit@1 | hit@5 | MRR |
|---|---|---|---|---|
| keyword | standard (30) | 0.80 | 0.97 | 0.87 |
| keyword | hard (18) | 0.50 | 0.83 | 0.66 |
| keyword + rerank | standard | 0.93 | 1.00 | 0.95 |
| keyword + rerank | hard | 1.00 | 1.00 | 1.00 |
| vector / hybrid / hybrid + rerank | both | skipped (no embedding model) | | |

| Answer arm (10 questions) | Faithfulness | Correctness | Citation rate | Avg latency | Avg tokens |
|---|---|---|---|---|---|
| RAG (search tool) | 0.90 | 0.93 | 1.00 | 16.5 s | 4,874 |
| Full context (no retrieval) | 0.90 | 0.97 | 1.00 | 10.1 s | 11,350 |

**How to read these honestly**

- The LLM reranker is the most valuable component: it lifts hit@1 from 0.80 to 0.93 on standard questions and from 0.50 to 1.00 on the hard paraphrased set.
- The judge is the same model as the chat model, which tends to grade itself generously; set `OPENAI_JUDGE_MODEL` to a different model for an independent judge. Sample sizes (10 to 30) are small, so numbers are indicative, not precise.
- With only 57 short chunks, stuffing the whole corpus into the prompt is a legitimate baseline: it scored slightly higher on correctness and ran faster here, at about 2.3x the tokens. RAG's advantage grows as the corpus outgrows the context window and as token cost matters.

---

## 13. Security

| Area | Implementation |
|---|---|
| Passwords | bcrypt with per-password salt |
| Sessions | JWT (HS256, python-jose); subject is the email; default lifetime 7 days; HTTP bearer scheme |
| AWS secrets | Validated with STS before saving; secret key encrypted at rest with Fernet; never logged |
| Data isolation | Chat tools and usage stats are filtered to the signed-in user's accounts (or the shared demo account) |
| Rate limiting | Per-user hourly chat limit (default 60) |
| Input limits | Question at most 2,000 characters; history at most 50 messages of 8,000 characters each; search query truncated to 300 characters |
| SQL | SQLAlchemy ORM and parameterized queries; keyword tsquery built only from `[a-z0-9]` tokens |
| CORS | Allows `http://localhost:5173` and `http://localhost:3000` only |
| Secrets | `.env` is gitignored; no key is ever committed |

**Honest gaps:** the default `JWT_SECRET_KEY` and `APP_ENCRYPTION_KEY` are development values and must be replaced for any real deployment; CORS is localhost-only; the cost-data, anomaly-detect, and seed routes are open demo routes without login (the data is the shared demo data); the AWS access key ID is stored in plain text (only the secret is encrypted).

---

## 14. Observability and operations

- **Request logging:** one line per request (method, path, status, latency). Development mode logs at DEBUG, which is very verbose (it includes provider request payloads).
- **Health:** `GET /health` (liveness) and `GET /health/ready` (also checks the database; 503 if not reachable).
- **Metrics:** `GET /metrics` in Prometheus format (request counts, latency histograms, status codes).
- **LLM traces:** every chat saves a `chat_traces` row (question, answer, tools used, citations, tokens, cost, latency, status). `GET /api/llm/usage` aggregates the current user's traces: requests, errors, tokens, cost, unpriced requests, p50 and p95 latency, average tool calls, cited answers, per-tool call counts, and recent requests. The UI shows this on the "AI usage" page.
- **Containers:** `docker compose up -d`; note that `docker compose restart` does **not** reload `.env`; use `docker compose up -d --force-recreate backend` after changing it.

---

## 15. Frontend

React 18 + TypeScript, built with Vite, charts with Recharts, icons from lucide-react.

| Screen | What it shows |
|---|---|
| Landing page | Product pitch and sign-in entry |
| Auth | Sign in and sign up |
| Onboarding tour | Short guided tour for first-time users |
| Dashboard | Seed demo data, KPI tiles, spend-by-service bar chart, daily trend line |
| Anomalies | Detect, list, and send to Slack |
| Chat | Streaming agent chat (below) |
| AI usage | Tokens, cost, latency, tool usage, recent requests; knowledge-base status and re-index |
| Settings | Connect AWS, sync costs, Slack webhook |

**Chat UI details**

- Uses `fetch` with a streaming body reader to parse SSE (the browser `EventSource` only supports GET). An `AbortController` powers the Stop button.
- Shows live **tool steps** ("Cost summary", "Knowledge base" with the query and result summary) while the model works.
- Renders a small markdown subset (headings, bullet and numbered lists, bold, inline code) and turns `[K#]` refs into citation badges that jump to the Sources panel.
- Shows a usage footer per answer (time, tokens, model calls).
- Suggestion chips for common questions; history is sent with each question.

---

## 16. API reference

| Method and path | Auth | Purpose |
|---|---|---|
| `GET /health`, `GET /health/ready`, `GET /metrics` | none | Probes and metrics |
| `POST /api/auth/signup`, `POST /api/auth/login` | none | Create account / log in, returns a JWT |
| `GET /api/auth/me`, `PATCH /api/auth/me` | JWT | Profile, Slack webhook, onboarding flag |
| `GET /api/accounts` | none | List accounts |
| `GET /api/accounts/me`, `POST /api/accounts/connect-aws`, `POST /api/accounts/sync` | JWT | Real AWS connection and cost sync |
| `POST /api/costs/seed`, `GET /api/costs`, `GET /api/costs/by-service`, `GET /api/costs/trend` | none | Demo data and cost aggregates |
| `POST /api/anomalies/detect`, `GET /api/anomalies`, `POST /api/anomalies/alert` | none (alert uses the user's webhook if signed in) | Anomaly detection and Slack alert |
| `POST /api/chat/ask` | JWT | Chat, one JSON response |
| `POST /api/chat/stream` | JWT | Chat as Server-Sent Events |
| `GET /api/knowledge/status`, `POST /api/knowledge/reindex`, `POST /api/knowledge/search` | JWT | Knowledge-base status, re-index, retrieval-only search |
| `GET /api/llm/usage` | JWT | Per-user LLM usage report |

Interactive docs: `/docs`.

---

## 17. Configuration reference

All values come from environment variables (read from `backend/.env`; real environment variables take precedence over the file).

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | sqlite file | Postgres URL (set in `.env`/compose) |
| `ENVIRONMENT` | development | Controls log level |
| `OPENAI_API_KEY` | empty | OpenAI key (chat disabled if neither OpenAI nor Azure is set) |
| `OPENAI_MODEL` | gpt-4o | Chat model, or the Azure **deployment name** |
| `AZURE_OPENAI_ENDPOINT` | empty | Set to switch all calls to Azure (portal URL works as is) |
| `AZURE_OPENAI_API_KEY` | empty | Azure key |
| `AZURE_OPENAI_API_VERSION` | 2024-10-21 | Used only for classic Azure endpoints |
| `LLM_CHAT_API` | auto | `chat`, `responses`, or `auto` |
| `LLM_SEND_TEMPERATURE` | auto | Force temperature on or off |
| `OPENAI_EMBEDDING_MODEL` | text-embedding-3-small | Embedding model or deployment; **empty = keyword-only** |
| `EMBEDDING_DIMENSIONS` | 1536 | Must match the vector column |
| `EMBEDDING_SUPPORTS_DIMENSIONS` | true | Set false for `text-embedding-ada-002` |
| `OPENAI_RERANK_MODEL`, `OPENAI_JUDGE_MODEL` | gpt-4o-mini (OpenAI) or chat deployment (Azure) | Reranker and eval judge |
| `RAG_RERANK` | true | Enable the LLM reranker |
| `RAG_CANDIDATES` | 20 | Candidates per retriever |
| `RAG_TOP_K` | 5 | Passages handed to the chat model |
| `CHAT_REQUESTS_PER_HOUR` | 60 | Per-user rate limit |
| `OPENAI_PRICING_OVERRIDES` | empty | JSON of `{model: [input_usd, output_usd]}` per 1M tokens |
| `SLACK_WEBHOOK_URL` | empty | Shared fallback webhook |
| `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES` | dev secret, HS256, 10080 | Token signing |
| `APP_ENCRYPTION_KEY` | dev key | Fernet key for AWS secrets |
| `BACKEND_PORT` (compose) | 8000 | Host port for the backend |
| `VITE_API_URL` (frontend) | http://localhost:8000 | Backend URL the browser calls |

---

## 18. Testing and CI

**Tests.** About 45 pytest tests run in roughly 11 seconds. A fake OpenAI client (`tests/fakes.py`) replaces the real provider, so no key or network is needed. SQLite in memory is used for speed; one Postgres-only test checks hybrid retrieval against the real pgvector database. `tests/conftest.py` pins the AI environment variables so tests never depend on a developer's local `.env`.

Covered areas: auth, accounts and AWS (mocked), anomalies, costs, health, chat and agent loop (tools, citations, streaming order, Azure client selection, temperature rules, v1 URL handling), RAG (chunking, ingestion, retrieval, RRF, rerank, keyword-only mode), usage reporting, eval metrics.

**CI (GitHub Actions, on push and pull request to `main`)**

1. **Backend tests:** real `pgvector/pgvector:pg16` service, `alembic upgrade head`, then `pytest`.
2. **RAG + agent evals:** runs `python -m evals.run --check` against real models only if an API-key secret is configured; otherwise skipped so forks still pass. Uploads the report.
3. **Frontend:** `tsc -b && vite build`.
4. **Docker build:** builds both images, gated on the jobs above.

Run locally: `docker compose exec -T backend python -m pytest -q`.

---

## 19. Known limitations and roadmap

**Limitations (today)**

- Vector and hybrid retrieval are off until an embedding model is configured; retrieval is keyword + rerank.
- The eval judge is the same model as the chat model (self-grading bias); eval sets are small.
- Chat latency is 5-27 s with a reasoning model; the model cost is shown as "unpriced" unless pricing overrides are set for the deployment name.
- Demo data is random and synthetic; the real AWS path is untested against a live account.
- Some routes are open; dev secrets and localhost CORS need changing for production.
- Cost data granularity is daily per service (no usage type, region, tags, or resource level).

**Roadmap to strengthen the RAG showcase**

1. Turn on embeddings and compare keyword, vector, hybrid, and hybrid + rerank using the existing evals.
2. **User document upload** with per-user filtering (runbooks, architecture notes, post-mortems).
3. **RAG-powered anomaly explanations:** retrieve the runbook section and similar past anomalies when a spike is flagged.
4. A larger public corpus (AWS Well-Architected cost guidance, pricing pages).
5. Query rewriting and multi-query retrieval; metadata filters; abstain when evidence is weak; verify that each citation supports its claim.
6. Independent judge model and larger golden sets; publish the comparison table.

---

## 20. Glossary

- **LLM:** large language model; here GPT-style models that read text and generate text.
- **RAG (retrieval-augmented generation):** fetch relevant passages from a knowledge base first, give them to the model, and have it answer from them (with citations) instead of from memory.
- **Agent / tool calling:** the model chooses functions to call; the server runs them and returns the results; the model continues.
- **Embedding:** a vector of numbers representing the meaning of text.
- **Vector search / cosine distance:** finding the stored vectors closest in direction to the query vector.
- **pgvector:** Postgres extension that stores vectors and searches them.
- **HNSW:** an approximate nearest-neighbor index (graph-based) for fast vector search.
- **Full-text search (FTS):** Postgres keyword search over tokenized text (`tsvector`, `tsquery`, GIN index).
- **Hybrid retrieval:** combining keyword and vector search.
- **RRF (Reciprocal Rank Fusion):** merging ranked lists using only their ranks.
- **Reranking:** a second pass (here an LLM) that reorders candidate passages by relevance.
- **Chunking:** splitting documents into passages sized for retrieval.
- **Context window:** the maximum text a model can read in one request.
- **Faithfulness / correctness / citation rate:** answer-quality metrics: supported by sources, matches the reference, cites when it should.
- **hit@k, recall@k, MRR:** retrieval metrics: a relevant result in the top k, the share of relevant sources found, and the average of 1/rank of the first relevant result.
- **SSE (Server-Sent Events):** one-way streaming from server to browser over HTTP.
- **Responses API:** OpenAI's newer API shape, required for function tools on some reasoning models.
- **Deployment name (Azure):** the name you gave a model deployment; used as the `model` value.
- **IsolationForest:** an unsupervised anomaly-detection algorithm that isolates unusual points quickly.
- **Fernet:** symmetric encryption from the `cryptography` library.

---

## 21. Interview talking points

1. **Why tools for numbers and RAG for advice?** Numbers are structured and exact, so SQL is more accurate than retrieval. Advice is unstructured text, which is what RAG is for.
2. **How do you stop the model inventing numbers or sources?** The prompt forbids guessing; figures come only from tool results; citations are verified server-side against refs that were actually retrieved.
3. **Why hybrid retrieval plus a reranker?** Vector search handles paraphrase, keyword search handles exact terms, RRF merges them without score calibration, and the reranker fixes ordering. The eval shows the reranker lifting hit@1 from 0.80 to 0.93 (standard) and 0.50 to 1.00 (hard).
4. **Is RAG even needed for a 57-chunk corpus?** The baseline comparison shows stuffing everything is competitive at this size (slightly better correctness, 2.3x the tokens); RAG pays off as the corpus grows. Being honest about this is a strength.
5. **How would it scale?** Incremental hash-based ingestion, batching, HNSW index, optional dimension reduction, metadata filters for multi-tenancy, caching; pgvector comfortably handles millions of vectors.
6. **How do you work across providers and models?** One LLM module hides OpenAI vs Azure, Chat Completions vs the Responses API, and model-specific parameter rules.
7. **How do you know it works?** A golden-set eval harness with retrieval and answer metrics and thresholds enforced in CI; fake-provider tests for everything else.
8. **What would you improve next?** Turn on embeddings, add per-user document upload with filtering, RAG-based anomaly explanations, an independent judge model, and production hardening.
