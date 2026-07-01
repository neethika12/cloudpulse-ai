from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import health, accounts, costs, chat, anomalies

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

app.include_router(health.router)
app.include_router(accounts.router)
app.include_router(costs.router)
app.include_router(chat.router)
app.include_router(anomalies.router)


@app.get("/")
def root():
    return {"message": "CloudPulse AI is running!", "status": "healthy"}