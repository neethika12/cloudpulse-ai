import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.logging_config import configure_logging
from app.routes import health, accounts, costs, chat, anomalies, auth

configure_logging()
logger = logging.getLogger("cloudpulse")

app = FastAPI(
    title="CloudPulse AI",
    description="AI-powered cloud cost monitoring platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    One structured log line per request: method, path, status, and latency. This is
    the cheapest form of observability - enough to spot slow endpoints or error spikes
    in `docker compose logs backend` without standing up a full logging stack.
    """
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "%s %s -> %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(costs.router)
app.include_router(chat.router)
app.include_router(anomalies.router)

# Exposes /metrics in Prometheus text format: request counts, latency histograms,
# and status codes per endpoint. Point a local Prometheus/Grafana stack at it, or
# just curl it directly - no external service required for this to work.
Instrumentator().instrument(app).expose(app)


@app.get("/")
def root():
    return {"message": "CloudPulse AI is running!", "status": "healthy"}
