from fastapi import FastAPI
from datetime import datetime, timezone

app = FastAPI(title="Backup Resilience Lab")


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "backup-resilience-lab",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
