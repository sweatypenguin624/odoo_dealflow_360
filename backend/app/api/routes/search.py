from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_internal_user
from app.models import User
from app.services import search_service

router = APIRouter(tags=["search"])


@router.get("/search", summary="Global search: customers, quotes, orders, products, invoices, subscriptions")
def global_search(q: str = Query(..., min_length=1, max_length=100), limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db), user: User = Depends(get_internal_user)):
    return search_service.search(db, user, q, limit)
