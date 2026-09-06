"""Fulfillment: plan -> reserve -> ship -> deliver, with backorders.

  suggest      : run the split engine over available stock; persist a plan
  override     : replace allocations by hand (warns about stock)
  confirm      : lock + re-check stock, reserve it (409 on shortage)
  ship         : consume reserved stock, create shipments
  deliver      : mark a shipment delivered (feeds delivery slippage)
  consolidate  : re-plan open backorders against stock that has arrived
"""

from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.errors import NotFoundError, StateTransitionError, ValidationError
from app.models import (
    FulfillmentPlan,
    FulfillmentPlanStatus,
    FulfillmentSplit,
    FulfillmentStatus,
    Quote,
    QuoteLine,
    QuoteStatus,
    Shipment,
    ShipmentStatus,
    SplitStatus,
    Stock,
    User,
    Warehouse,
)
from app.services import audit_service, inventory_service
from app.services.fulfillment_engine import LineToFulfill, WarehouseStockInput, plan_fulfillment
from app.services.inventory_service import StockShortage
from app.services.notifications import NotificationService
from app.services.numbering import next_number

FULFILLABLE = frozenset({QuoteStatus.confirmed})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def latest_plan(db: Session, quote_id: int) -> Optional[FulfillmentPlan]:
    return (
        db.query(FulfillmentPlan)
        .options(joinedload(FulfillmentPlan.splits).joinedload(FulfillmentSplit.quote_line), joinedload(FulfillmentPlan.shipments))
        .populate_existing()
        .filter(FulfillmentPlan.quote_id == quote_id, FulfillmentPlan.status != FulfillmentPlanStatus.cancelled)
        .order_by(FulfillmentPlan.id.desc())
        .first()
    )


def load_stock_by_product(db: Session, product_ids: List[int]) -> Dict[int, List[WarehouseStockInput]]:
    if not product_ids:
        return {}
    rows = (
        db.query(Stock, Warehouse)
        .join(Warehouse, Stock.warehouse_id == Warehouse.id)
        .filter(Stock.product_id.in_(product_ids), Warehouse.is_active.is_(True))
        .all()
    )
    out: Dict[int, List[WarehouseStockInput]] = {}
    for stock, warehouse in rows:
        out.setdefault(stock.product_id, []).append(
            WarehouseStockInput(warehouse_id=warehouse.id, shipping_cost_weight=float(warehouse.shipping_cost_weight), quantity_available=stock.quantity_available)
        )
    return out


def _assert_fulfillable(quote: Quote) -> None:
    if quote.status not in FULFILLABLE:
        raise StateTransitionError(
            "Quote must be confirmed (approved and accepted by the customer) before fulfillment can be planned.",
            code="not_fulfillable",
        )


def needs_shipping(line: QuoteLine) -> bool:
    return not line.is_recurring and bool(line.product.is_stocked)


def physical_lines(quote: Quote) -> List[LineToFulfill]:
    return [LineToFulfill(quote_line_id=l.id, product_id=l.product_id, quantity_needed=l.quantity) for l in quote.lines if needs_shipping(l)]


def backorder_summary(plan: FulfillmentPlan) -> List[str]:
    out = []
    for split in plan.splits:
        if split.is_backorder and split.status != SplitStatus.cancelled:
            out.append(f"Line {split.quote_line_id} ({split.quote_line.description or 'Product ' + str(split.quote_line.product_id)}): {split.quantity_fulfilled} of {split.quote_line.quantity} units backordered")
    return out


def _update_quote_status(db: Session, quote: Quote, plan: FulfillmentPlan) -> None:
    active = [s for s in plan.splits if s.status != SplitStatus.cancelled]
    if not active:
        quote.fulfillment_status = FulfillmentStatus.not_started
        return
    shipped = [s for s in active if s.status == SplitStatus.shipped]
    reserved = [s for s in active if s.status == SplitStatus.reserved]
    backordered = [s for s in active if s.status == SplitStatus.backordered]
    if plan.status in (FulfillmentPlanStatus.suggested, FulfillmentPlanStatus.manually_overridden):
        quote.fulfillment_status = FulfillmentStatus.planned
    elif shipped and not reserved and not backordered:
        delivered = all(sh.status == ShipmentStatus.delivered for sh in plan.shipments) and plan.shipments
        quote.fulfillment_status = FulfillmentStatus.delivered if delivered else FulfillmentStatus.shipped
    elif shipped:
        quote.fulfillment_status = FulfillmentStatus.partially_shipped
    else:
        quote.fulfillment_status = FulfillmentStatus.reserved
    quote.last_activity_at = _now()


def suggest(db: Session, quote: Quote, actor: Optional[User]) -> FulfillmentPlan:
    _assert_fulfillable(quote)
    existing = latest_plan(db, quote.id)
    if existing is not None and existing.status not in (FulfillmentPlanStatus.suggested, FulfillmentPlanStatus.manually_overridden):
        raise StateTransitionError("Stock is already reserved or shipped for this order; re-planning is not possible.", code="plan_locked")
    lines = physical_lines(quote)
    if not lines:
        raise ValidationError("This order has no stocked lines to ship (services, licences and subscriptions are fulfilled on confirmation).")
    result = plan_fulfillment(lines, load_stock_by_product(db, [l.product_id for l in lines]))
    if existing is not None:
        db.delete(existing)
        db.flush()
    plan = FulfillmentPlan(quote_id=quote.id, status=FulfillmentPlanStatus.suggested, created_by_user_id=actor.id if actor else None)
    db.add(plan)
    db.flush()
    for a in result.allocations:
        db.add(
            FulfillmentSplit(
                fulfillment_plan_id=plan.id,
                quote_line_id=a.quote_line_id,
                warehouse_id=a.warehouse_id,
                quantity_fulfilled=a.quantity_fulfilled,
                is_backorder=a.is_backorder,
                status=SplitStatus.backordered if a.is_backorder else SplitStatus.planned,
            )
        )
    db.flush()
    plan = latest_plan(db, quote.id)
    _update_quote_status(db, quote, plan)
    audit_service.record(
        db, "fulfillment_suggested", actor=actor, quote_id=quote.id, entity_type="fulfillment_plan", entity_id=plan.id,
        reason=f"{result.total_shipments} shipment(s); " + ("; ".join(result.backorder_summary) if result.backorder_summary else "no backorders"),
    )
    return plan


def override(db: Session, quote: Quote, actor: Optional[User], allocations: List[dict]) -> tuple[FulfillmentPlan, Dict[int, str]]:
    plan = latest_plan(db, quote.id)
    if plan is None:
        raise NotFoundError("No fulfillment plan found for this quote")
    if plan.status not in (FulfillmentPlanStatus.suggested, FulfillmentPlanStatus.manually_overridden):
        raise StateTransitionError("Stock is already reserved for this plan; release it before overriding.", code="plan_locked")
    lines = {l.id: l for l in quote.lines if needs_shipping(l)}
    totals: Dict[int, int] = {}
    for a in allocations:
        totals[a["quote_line_id"]] = totals.get(a["quote_line_id"], 0) + a["quantity_fulfilled"]
    mismatches = []
    for line_id, line in lines.items():
        provided = totals.get(line_id, 0)
        if provided != line.quantity:
            mismatches.append(f"Line {line_id}: allocations sum to {provided} but {line.quantity} units are needed")
    for line_id in set(totals) - set(lines):
        mismatches.append(f"Line {line_id} does not belong to quote {quote.id}")
    for a in allocations:
        if a.get("warehouse_id") is not None and db.get(Warehouse, a["warehouse_id"]) is None:
            mismatches.append(f"Warehouse {a['warehouse_id']} does not exist")
        if a["quantity_fulfilled"] <= 0:
            mismatches.append("Allocation quantities must be positive")
    if mismatches:
        raise ValidationError("Allocation quantities do not match line requirements: " + "; ".join(mismatches), code="allocation_mismatch")

    db.query(FulfillmentSplit).filter(FulfillmentSplit.fulfillment_plan_id == plan.id).delete(synchronize_session=False)
    for a in allocations:
        is_backorder = a.get("warehouse_id") is None or a.get("is_backorder", False)
        db.add(
            FulfillmentSplit(
                fulfillment_plan_id=plan.id,
                quote_line_id=a["quote_line_id"],
                warehouse_id=None if is_backorder else a["warehouse_id"],
                quantity_fulfilled=a["quantity_fulfilled"],
                is_backorder=is_backorder,
                status=SplitStatus.backordered if is_backorder else SplitStatus.planned,
                expected_date=a.get("expected_date"),
            )
        )
    plan.status = FulfillmentPlanStatus.manually_overridden
    db.flush()
    plan = latest_plan(db, quote.id)
    _update_quote_status(db, quote, plan)
    audit_service.record(db, "fulfillment_overridden", actor=actor, quote_id=quote.id, entity_type="fulfillment_plan", entity_id=plan.id, reason="Manually overridden by operations")

    warnings: Dict[int, str] = {}
    lookup = {(s.warehouse_id, s.product_id): s.quantity_available for s in db.query(Stock).filter(Stock.warehouse_id.in_([a.get("warehouse_id") for a in allocations if a.get("warehouse_id")] or [0])).all()}
    for split in plan.splits:
        if split.is_backorder:
            continue
        available = lookup.get((split.warehouse_id, split.quote_line.product_id))
        if available is not None and split.quantity_fulfilled > available:
            warnings[split.id] = f"Requested {split.quantity_fulfilled} exceeds known available stock ({available}) at warehouse {split.warehouse_id}"
        elif available is None:
            warnings[split.id] = f"No stock record at warehouse {split.warehouse_id}"
    return plan, warnings


def confirm(db: Session, quote: Quote, actor: Optional[User]) -> FulfillmentPlan:
    """Reserve stock for every non-backorder split, atomically."""
    plan = latest_plan(db, quote.id)
    if plan is None or plan.status not in (FulfillmentPlanStatus.suggested, FulfillmentPlanStatus.manually_overridden):
        raise StateTransitionError("No suggested fulfillment plan exists for this quote", code="no_plan")
    shippable = [s for s in plan.splits if not s.is_backorder]
    # Aggregate per stock row so a shortage is reported once, then lock + reserve.
    needed: Dict[tuple, int] = {}
    for s in shippable:
        key = (s.warehouse_id, s.quote_line.product_id)
        needed[key] = needed.get(key, 0) + s.quantity_fulfilled
    shortages = []
    for (warehouse_id, product_id), qty in needed.items():
        stock = inventory_service.get_stock(db, warehouse_id, product_id, for_update=True)
        if stock is None:
            shortages.append(f"no stock record for product {product_id} at warehouse {warehouse_id}")
        elif stock.quantity_available < qty:
            shortages.append(f"Warehouse {stock.warehouse.name}/{stock.product.name}: needs {qty} but only {stock.quantity_available} available")
    if shortages:
        db.rollback()
        raise StockShortage("Stock insufficient to confirm fulfillment: " + "; ".join(shortages))
    for (warehouse_id, product_id), qty in needed.items():
        inventory_service.reserve(db, warehouse_id, product_id, qty, "fulfillment_plan", plan.id, actor)
    for s in shippable:
        s.status = SplitStatus.reserved
    plan.status = FulfillmentPlanStatus.confirmed
    db.flush()
    plan = latest_plan(db, quote.id)
    _update_quote_status(db, quote, plan)
    shipment_count = len({s.warehouse_id for s in shippable})
    backorder_count = len([s for s in plan.splits if s.is_backorder])
    audit_service.record(
        db, "fulfillment_confirmed", actor=actor, quote_id=quote.id, entity_type="fulfillment_plan", entity_id=plan.id,
        reason=f"{shipment_count} shipment(s) reserved; {backorder_count} line(s) backordered.",
    )
    if backorder_count:
        _notify_backorder(db, quote, plan, actor)
    return plan


def _notify_backorder(db: Session, quote: Quote, plan: FulfillmentPlan, actor: Optional[User]) -> None:
    notifications = NotificationService(db)
    from app.core.permissions import Role

    recipients = ([quote.owner] if quote.owner else []) + notifications.users_with_role(Role.finance)
    notifications.notify(
        recipients,
        type="backorder",
        title=f"Backorder on {quote.order_number or quote.quote_number}",
        body="; ".join(backorder_summary(plan)),
        entity_type="quote",
        entity_id=quote.id,
        triggered_by=actor,
        email_template="generic",
        email_context={"url": notifications.frontend_url(f"/workspace/quotations/{quote.id}/fulfillment")},
    )


def ship(db: Session, quote: Quote, actor: Optional[User], warehouse_id: Optional[int] = None, expected_date: Optional[date] = None, tracking_reference: Optional[str] = None) -> List[Shipment]:
    plan = latest_plan(db, quote.id)
    if plan is None or plan.status not in (FulfillmentPlanStatus.confirmed, FulfillmentPlanStatus.partially_shipped):
        raise StateTransitionError("Stock must be reserved (plan confirmed) before shipping.", code="not_reserved")
    to_ship = [s for s in plan.splits if s.status == SplitStatus.reserved and (warehouse_id is None or s.warehouse_id == warehouse_id)]
    if not to_ship:
        raise StateTransitionError("Nothing is reserved and waiting to ship.", code="nothing_to_ship")
    by_warehouse: Dict[int, List[FulfillmentSplit]] = {}
    for s in to_ship:
        by_warehouse.setdefault(s.warehouse_id, []).append(s)
    shipments = []
    for wh_id, splits in by_warehouse.items():
        shipment = Shipment(
            shipment_number=next_number(db, "shipment"),
            fulfillment_plan_id=plan.id,
            quote_id=quote.id,
            warehouse_id=wh_id,
            status=ShipmentStatus.shipped,
            promised_date=quote.promised_delivery_date,
            expected_date=expected_date or plan.expected_delivery_date or quote.expected_delivery_date,
            shipped_at=_now(),
            tracking_reference=tracking_reference,
        )
        db.add(shipment)
        db.flush()
        for s in splits:
            inventory_service.consume(db, wh_id, s.quote_line.product_id, s.quantity_fulfilled, "shipment", shipment.id, actor)
            s.status = SplitStatus.shipped
            s.shipment_id = shipment.id
        shipments.append(shipment)
    remaining = [s for s in plan.splits if s.status in (SplitStatus.reserved, SplitStatus.backordered)]
    plan.status = FulfillmentPlanStatus.partially_shipped if remaining else FulfillmentPlanStatus.shipped
    db.flush()
    plan = latest_plan(db, quote.id)
    _update_quote_status(db, quote, plan)
    if expected_date:
        quote.expected_delivery_date = expected_date
    audit_service.record(
        db, "shipped", actor=actor, quote_id=quote.id, entity_type="fulfillment_plan", entity_id=plan.id,
        reason=", ".join(f"{sh.shipment_number} from warehouse {sh.warehouse_id}" for sh in shipments),
    )
    from app.services import invoice_service

    invoice_service.refresh_quote_billing_status(db, quote)
    return shipments


def deliver(db: Session, quote: Quote, shipment_id: int, actor: Optional[User], delivered_at: Optional[datetime] = None) -> Shipment:
    shipment = db.get(Shipment, shipment_id)
    if shipment is None or shipment.quote_id != quote.id:
        raise NotFoundError("Shipment not found on this order")
    if shipment.status != ShipmentStatus.shipped:
        raise StateTransitionError("Only shipped shipments can be marked delivered.", code="invalid_transition")
    shipment.status = ShipmentStatus.delivered
    shipment.delivered_at = delivered_at or _now()
    db.flush()
    plan = latest_plan(db, quote.id)
    _update_quote_status(db, quote, plan)
    if quote.fulfillment_status == FulfillmentStatus.delivered:
        quote.actual_delivery_date = shipment.delivered_at.date()
    audit_service.record(db, "delivered", actor=actor, quote_id=quote.id, entity_type="shipment", entity_id=shipment.id, reason=f"{shipment.shipment_number} delivered")
    return shipment


def consolidate_backorders(db: Session, quote: Quote, actor: Optional[User]) -> dict:
    """Try to fill open backorders from stock that has since arrived."""
    plan = latest_plan(db, quote.id)
    if plan is None:
        raise NotFoundError("No fulfillment plan found for this quote")
    if plan.status in (FulfillmentPlanStatus.suggested, FulfillmentPlanStatus.manually_overridden):
        raise StateTransitionError("Confirm the plan (reserve stock) before consolidating backorders.", code="not_reserved")
    open_backorders = [s for s in plan.splits if s.status == SplitStatus.backordered]
    if not open_backorders:
        raise StateTransitionError("There are no open backorders on this order.", code="no_backorders")
    lines = [LineToFulfill(quote_line_id=s.quote_line_id, product_id=s.quote_line.product_id, quantity_needed=s.quantity_fulfilled) for s in open_backorders]
    result = plan_fulfillment(lines, load_stock_by_product(db, [l.product_id for l in lines]))
    filled = 0
    new_splits = []
    for split in open_backorders:
        allocated = [a for a in result.allocations if a.quote_line_id == split.quote_line_id and not a.is_backorder]
        taken = 0
        for a in allocated:
            inventory_service.reserve(db, a.warehouse_id, split.quote_line.product_id, a.quantity_fulfilled, "fulfillment_plan", plan.id, actor)
            new = FulfillmentSplit(
                fulfillment_plan_id=plan.id, quote_line_id=split.quote_line_id, warehouse_id=a.warehouse_id,
                quantity_fulfilled=a.quantity_fulfilled, is_backorder=False, status=SplitStatus.reserved,
            )
            db.add(new)
            new_splits.append(new)
            taken += a.quantity_fulfilled
        filled += taken
        if taken >= split.quantity_fulfilled:
            db.delete(split)
        elif taken > 0:
            split.quantity_fulfilled -= taken
    db.flush()
    plan = latest_plan(db, quote.id)
    if plan.status == FulfillmentPlanStatus.shipped:
        plan.status = FulfillmentPlanStatus.partially_shipped
    _update_quote_status(db, quote, plan)
    remaining = sum(s.quantity_fulfilled for s in plan.splits if s.status == SplitStatus.backordered)
    audit_service.record(
        db, "backorder_consolidated", actor=actor, quote_id=quote.id, entity_type="fulfillment_plan", entity_id=plan.id,
        reason=f"{filled} backordered unit(s) reserved from incoming stock; {remaining} still outstanding",
    )
    return {"plan": plan, "units_reserved": filled, "units_still_backordered": remaining, "new_split_ids": [s.id for s in new_splits]}


def release_plan(db: Session, quote: Quote, actor: Optional[User], reason: Optional[str]) -> None:
    """Cancel a confirmed-but-unshipped plan and give the stock back."""
    plan = latest_plan(db, quote.id)
    if plan is None:
        raise NotFoundError("No fulfillment plan found for this quote")
    if any(s.status == SplitStatus.shipped for s in plan.splits):
        raise StateTransitionError("Shipped allocations cannot be released.", code="already_shipped")
    for s in plan.splits:
        if s.status == SplitStatus.reserved:
            inventory_service.release(db, s.warehouse_id, s.quote_line.product_id, s.quantity_fulfilled, "fulfillment_plan", plan.id, actor)
        s.status = SplitStatus.cancelled
    plan.status = FulfillmentPlanStatus.cancelled
    quote.fulfillment_status = FulfillmentStatus.not_started
    audit_service.record(db, "fulfillment_released", actor=actor, quote_id=quote.id, entity_type="fulfillment_plan", entity_id=plan.id, reason=reason)


def open_backorders(db: Session):
    return (
        db.query(FulfillmentSplit)
        .options(joinedload(FulfillmentSplit.quote_line).joinedload(QuoteLine.product), joinedload(FulfillmentSplit.plan).joinedload(FulfillmentPlan.quote).joinedload(Quote.customer))
        .join(FulfillmentPlan, FulfillmentSplit.fulfillment_plan_id == FulfillmentPlan.id)
        .filter(FulfillmentSplit.status == SplitStatus.backordered, FulfillmentPlan.status != FulfillmentPlanStatus.cancelled)
        .order_by(FulfillmentSplit.id)
    )
