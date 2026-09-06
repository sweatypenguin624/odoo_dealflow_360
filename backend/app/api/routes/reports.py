from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.errors import NotFoundError
from app.core.permissions import Permission
from app.models import User
from app.services import export_service
from app.services.reporting_service import REPORTS, ReportFilters

router = APIRouter(prefix="/reports", tags=["reports"])


def report_filters(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    owner_user_id: Optional[int] = None,
    team: Optional[str] = None,
    customer_id: Optional[int] = None,
    tier_id: Optional[int] = None,
    product_id: Optional[int] = None,
    category_id: Optional[int] = None,
    quote_status: Optional[str] = None,
    approval_status: Optional[str] = None,
    fulfillment_status: Optional[str] = None,
    invoice_status: Optional[str] = None,
) -> ReportFilters:
    return ReportFilters(
        date_from=date_from, date_to=date_to, owner_user_id=owner_user_id, team=team, customer_id=customer_id, tier_id=tier_id, product_id=product_id,
        category_id=category_id, quote_status=quote_status, approval_status=approval_status, fulfillment_status=fulfillment_status, invoice_status=invoice_status,
    )


@router.get("", summary="Available reports")
def list_reports(_: User = Depends(require_permission(Permission.report_read))):
    return [{"name": n, "title": n.replace("-", " ").title()} for n in REPORTS]


@router.get("/{name}", summary="Run a report with filters")
def run_report(name: str, filters: ReportFilters = Depends(report_filters), db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.report_read))):
    fn = REPORTS.get(name)
    if fn is None:
        raise NotFoundError(f"Unknown report '{name}'")
    result = fn(db, filters, user)
    result["filters"] = filters.describe()
    return result


@router.get("/{name}/export", summary="Export a report as csv / xlsx / pdf (respects the same filters)")
def export_report(
    name: str, format: str = Query("csv", pattern="^(csv|xlsx|pdf)$"), filters: ReportFilters = Depends(report_filters),
    db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.report_read)),
):
    fn = REPORTS.get(name)
    if fn is None:
        raise NotFoundError(f"Unknown report '{name}'")
    result = fn(db, filters, user)
    exported = export_service.export(format, f"{name}-report", f"{name.replace('-', ' ').title()} report", result["columns"], result["rows"], result.get("summary"), filters.describe())
    return Response(content=exported.content, media_type=exported.content_type, headers={"Content-Disposition": f'attachment; filename="{exported.filename}"'})
