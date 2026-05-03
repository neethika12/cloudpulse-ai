from fastapi import FastAPI
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Create the FastAPI app
app = FastAPI(
    title="CloudPulse AI",
    description="AI-powered cloud cost monitoring platform",
    version="1.0.0"
)

# Your first endpoint
@app.get("/")
def root():
    return {
        "message": "CloudPulse AI is running!",
        "status": "healthy"
    }

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "cloudpulse-ai-backend"
    }