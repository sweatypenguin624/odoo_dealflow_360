from typing import Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_permission
from app.core.money import D
from app.core.pagination import Page, PageParams, paginate_query
from app.core.permissions import Permission
from app.models import (
    Customer,
    FulfillmentPlan,
    FulfillmentPlanStatus,
    FulfillmentSplit,
    Quote,
    QuoteStatus,
    Shipment,
    SplitStatus,
    User,
    Warehouse,
)
from app.schemas.fulfillment import (
    BackorderOut,
    ConsolidateResult,
    DeliverRequest,
    FulfillmentListItem,
    FulfillmentPlanOut,
    OverrideRequest,
    ShipRequest,
    ShipmentOut,
    SplitOut,
)
from app.services import fulfillment_service, inventory_service, quote_service

router = APIRouter(tags=["fulfillment"])


def _plan_out(db: Session, plan: FulfillmentPlan, user: Optional[User] = None, warnings: Optional[Dict[int, str]] = None) -> FulfillmentPlanOut:
    warehouses = {w.id: w.name for w in db.query(Warehouse).all()}
    splits = [
        SplitOut(
            id=s.id, quote_line_id=s.quote_line_id, product_id=s.quote_line.product_id, product_name=s.quote_line.description or s.quote_line.product.name,
            warehouse_id=s.warehouse_id, warehouse_name=warehouses.get(s.warehouse_id), quantity_fulfilled=s.quantity_fulfilled,
            is_backorder=s.is_backorder, status=s.status.value, shipment_id=s.shipment_id, expected_date=s.expected_date,
            warning=(warnings or {}).get(s.id),
        )
        for s in plan.splits
        if s.status != SplitStatus.cancelled
    ]
    units_by_shipment: Dict[int, int] = {}
    for s in plan.splits:
        if s.shipment_id:
            units_by_shipment[s.shipment_id] = units_by_shipment.get(s.shipment_id, 0) + s.quantity_fulfilled
    shipments = [
        ShipmentOut.model_validate(sh).model_copy(update={"warehouse_name": warehouses.get(sh.warehouse_id, ""), "units": units_by_shipment.get(sh.id, 0)})
        for sh in sorted(plan.shipments, key=lambda x: x.id)
    ]
    actions = []
    if plan.status in (FulfillmentPlanStatus.suggested, FulfillmentPlanStatus.manually_overridden):
        actions += ["confirm", "override", "resuggest"]
    if any(s.status == SplitStatus.reserved for s in plan.splits):
        actions.append("ship")
    if plan.status not in (FulfillmentPlanStatus.suggested, FulfillmentPlanStatus.manually_overridden) and any(s.status == SplitStatus.backordered for s in plan.splits):
        actions.append("consolidate")
    if plan.status == FulfillmentPlanStatus.confirmed and not any(s.status == SplitStatus.shipped for s in plan.splits):
        actions.append("release")
    if any(sh.status.value == "shipped" for sh in plan.shipments):
        actions.append("deliver")
    return FulfillmentPlanOut(
        id=plan.id, quote_id=plan.quote_id, status=plan.status.value, splits=splits, shipments=shipments,
        backorder_summary=fulfillment_service.backorder_summary(plan),
        total_shipments=len({s.warehouse_id for s in plan.splits if not s.is_backorder and s.status != SplitStatus.cancelled}),
        units_reserved=sum(s.quantity_fulfilled for s in plan.splits if s.status == SplitStatus.reserved),
        units_shipped=sum(s.quantity_fulfilled for s in plan.splits if s.status == SplitStatus.shipped),
        units_backordered=sum(s.quantity_fulfilled for s in plan.splits if s.status == SplitStatus.backordered),
        expected_delivery_date=plan.expected_delivery_date or plan.quote.expected_delivery_date,
        available_actions=actions,
    )


def _quote(db: Session, quote_id: int, user: User) -> Quote:
    quote = quote_service.load_quote(db, quote_id)
    quote_service.assert_can_view(quote, user)
    return quote


@router.get("/fulfillment", response_model=Page[FulfillmentListItem], summary="Orders and their fulfillment state (one query)")
def list_fulfillment(
    params: PageParams = Depends(),
    q: Optional[str] = None,
    fulfillment_status: Optional[str] = None,
    only_backorders: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.fulfillment_read)),
):
    latest_plan = (
        db.query(FulfillmentPlan.quote_id, func.max(FulfillmentPlan.id).label("plan_id"))
        .filter(FulfillmentPlan.status != FulfillmentPlanStatus.cancelled)
        .group_by(FulfillmentPlan.quote_id)
        .subquery()
    )
    backorders = (
        db.query(FulfillmentSplit.fulfillment_plan_id, func.sum(FulfillmentSplit.quantity_fulfilled).label("units"))
        .filter(FulfillmentSplit.status == SplitStatus.backordered)
        .group_by(FulfillmentSplit.fulfillment_plan_id)
        .subquery()
    )
    shipments = db.query(Shipment.quote_id, func.count(Shipment.id).label("count")).group_by(Shipment.quote_id).subquery()
    query = (
        quote_service.visible_quotes_query(db, user)
        .filter(Quote.status == QuoteStatus.confirmed)
        .outerjoin(latest_plan, latest_plan.c.quote_id == Quote.id)
        .outerjoin(FulfillmentPlan, FulfillmentPlan.id == latest_plan.c.plan_id)
        .outerjoin(backorders, backorders.c.fulfillment_plan_id == FulfillmentPlan.id)
        .outerjoin(shipments, shipments.c.quote_id == Quote.id)
        .add_columns(FulfillmentPlan.status, backorders.c.units, shipments.c.count)
    )
    if q:
        like = f"%{q.strip()}%"
        query = query.join(Customer, Quote.customer_id == Customer.id).filter((Quote.quote_number.ilike(like)) | (Quote.order_number.ilike(like)) | (Customer.name.ilike(like)))
    if fulfillment_status:
        query = query.filter(Quote.fulfillment_status == fulfillment_status)
    if only_backorders:
        query = query.filter(backorders.c.units > 0)
    query = query.order_by(Quote.confirmed_at.desc().nullslast(), Quote.id.desc())
    rows, total = paginate_query(query, params)
    items = [
        FulfillmentListItem(
            quote_id=quote.id, quote_number=quote.quote_number, order_number=quote.order_number, customer_name=quote.customer.name,
            owner_name=quote.owner.full_name if quote.owner else None, quote_status=quote.status.value, fulfillment_status=quote.fulfillment_status.value,
            plan_status=plan_status.value if plan_status else None, total=D(quote.total), promised_delivery_date=quote.promised_delivery_date,
            expected_delivery_date=quote.expected_delivery_date, confirmed_at=quote.confirmed_at, units_backordered=int(units or 0), shipment_count=int(count or 0),
        )
        for quote, plan_status, units, count in rows
    ]
    return Page.build(items, total, params)


@router.get("/fulfillment/backorders", response_model=Page[BackorderOut])
def list_backorders(params: PageParams = Depends(), db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.fulfillment_read))):
    rows, total = paginate_query(fulfillment_service.open_backorders(db), params)
    available = inventory_service.available_by_product(db, [s.quote_line.product_id for s in rows])
    items = [
        BackorderOut(
            split_id=s.id, quote_id=s.plan.quote_id, quote_number=s.plan.quote.quote_number, order_number=s.plan.quote.order_number,
            customer_name=s.plan.quote.customer.name, product_id=s.quote_line.product_id, product_name=s.quote_line.product.name, sku=s.quote_line.product.sku,
            quantity=s.quantity_fulfilled, expected_date=s.expected_date, available_now=available.get(s.quote_line.product_id, 0),
            can_consolidate=available.get(s.quote_line.product_id, 0) > 0, promised_delivery_date=s.plan.quote.promised_delivery_date,
        )
        for s in rows
    ]
    return Page.build(items, total, params)


@router.get("/quotes/{quote_id}/fulfillment", response_model=FulfillmentPlanOut)
def get_plan(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.fulfillment_read))):
    quote = _quote(db, quote_id, user)
    plan = fulfillment_service.latest_plan(db, quote.id)
    if plan is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("No fulfillment plan found for this quote")
    return _plan_out(db, plan, user)


@router.post("/quotes/{quote_id}/fulfillment/suggest", response_model=FulfillmentPlanOut)
def suggest(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.fulfillment_manage, Permission.fulfillment_read))):
    quote = _quote(db, quote_id, user)
    plan = fulfillment_service.suggest(db, quote, user)
    db.commit()
    return _plan_out(db, fulfillment_service.latest_plan(db, quote.id), user)


@router.post("/quotes/{quote_id}/fulfillment/confirm", response_model=FulfillmentPlanOut, summary="Reserve stock for the plan (locks + re-checks inventory)")
def confirm(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.fulfillment_manage, Permission.fulfillment_read))):
    quote = _quote(db, quote_id, user)
    fulfillment_service.confirm(db, quote, user)
    db.commit()
    return _plan_out(db, fulfillment_service.latest_plan(db, quote.id), user)


@router.patch("/quotes/{quote_id}/fulfillment/override", response_model=FulfillmentPlanOut)
def override(quote_id: int, payload: OverrideRequest, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.fulfillment_manage))):
    quote = _quote(db, quote_id, user)
    plan, warnings = fulfillment_service.override(db, quote, user, [a.model_dump() for a in payload.allocations])
    db.commit()
    return _plan_out(db, fulfillment_service.latest_plan(db, quote.id), user, warnings)


@router.post("/quotes/{quote_id}/fulfillment/ship", response_model=FulfillmentPlanOut, summary="Ship reserved units (consumes stock, creates shipments)")
def ship(quote_id: int, payload: ShipRequest = ShipRequest(), db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.fulfillment_manage))):
    quote = _quote(db, quote_id, user)
    fulfillment_service.ship(db, quote, user, payload.warehouse_id, payload.expected_date, payload.tracking_reference)
    db.commit()
    return _plan_out(db, fulfillment_service.latest_plan(db, quote.id), user)


@router.post("/quotes/{quote_id}/fulfillment/shipments/{shipment_id}/deliver", response_model=FulfillmentPlanOut)
def deliver(quote_id: int, shipment_id: int, payload: DeliverRequest = DeliverRequest(), db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.fulfillment_manage))):
    quote = _quote(db, quote_id, user)
    fulfillment_service.deliver(db, quote, shipment_id, user, payload.delivered_at)
    db.commit()
    return _plan_out(db, fulfillment_service.latest_plan(db, quote.id), user)


@router.post("/quotes/{quote_id}/fulfillment/consolidate-backorders", response_model=ConsolidateResult, summary="Fill open backorders from stock that has arrived")
def consolidate(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.fulfillment_manage))):
    quote = _quote(db, quote_id, user)
    result = fulfillment_service.consolidate_backorders(db, quote, user)
    db.commit()
    return ConsolidateResult(plan=_plan_out(db, fulfillment_service.latest_plan(db, quote.id), user), units_reserved=result["units_reserved"], units_still_backordered=result["units_still_backordered"])


@router.post("/quotes/{quote_id}/fulfillment/release", response_model=FulfillmentPlanOut, summary="Release reserved stock and cancel the plan")
def release(quote_id: int, reason: Optional[str] = Query(None), db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.fulfillment_manage))):
    quote = _quote(db, quote_id, user)
    fulfillment_service.release_plan(db, quote, user, reason)
    db.commit()
    plan = db.query(FulfillmentPlan).filter(FulfillmentPlan.quote_id == quote.id).order_by(FulfillmentPlan.id.desc()).first()
    return _plan_out(db, plan, user)
