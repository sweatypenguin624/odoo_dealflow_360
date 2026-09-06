from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
def health():
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@router.get("/ready", summary="Readiness probe (checks the database)")
def ready(response: Response, db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        response.status_code = 503
        return {"status": "unavailable", "database": "down"}
    return {"status": "ready", "database": "ok"}
