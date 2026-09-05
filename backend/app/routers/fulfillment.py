from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    AuditLog,
    FulfillmentPlan,
    FulfillmentPlanStatus,
    FulfillmentSplit,
    Quote,
    QuoteLine,
    QuoteStatus,
    Stock,
    Warehouse,
)
from app.services.fulfillment_engine import WarehouseStockInput, plan_fulfillment
from app.services.quote_loader import build_fulfillment_lines

router = APIRouter(tags=["fulfillment"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---- Warehouse / Stock CRUD ----


class WarehouseCreate(BaseModel):
    name: str
    shipping_cost_weight: float


class WarehouseResponse(BaseModel):
    id: int
    name: str
    shipping_cost_weight: float

    class Config:
        from_attributes = True


@router.post("/warehouses", response_model=WarehouseResponse)
def create_warehouse(payload: WarehouseCreate, db: Session = Depends(get_db)):
    warehouse = Warehouse(name=payload.name, shipping_cost_weight=payload.shipping_cost_weight)
    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)
    return warehouse


@router.get("/warehouses", response_model=List[WarehouseResponse])
def list_warehouses(db: Session = Depends(get_db)):
    # Frontend gap-fill (Phase 8): FulfillmentSplit only ever carries a
    # warehouse_id - this is what lets the UI resolve it to a name.
    return db.query(Warehouse).all()


class StockUpsert(BaseModel):
    product_id: int
    quantity_available: int


class StockResponse(BaseModel):
    id: int
    warehouse_id: int
    product_id: int
    quantity_available: int

    class Config:
        from_attributes = True


@router.post("/warehouses/{warehouse_id}/stock", response_model=StockResponse)
def upsert_stock(warehouse_id: int, payload: StockUpsert, db: Session = Depends(get_db)):
    warehouse = db.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    stock = (
        db.query(Stock)
        .filter(Stock.warehouse_id == warehouse_id, Stock.product_id == payload.product_id)
        .first()
    )
    if stock is None:
        stock = Stock(
            warehouse_id=warehouse_id,
            product_id=payload.product_id,
            quantity_available=payload.quantity_available,
        )
        db.add(stock)
    else:
        stock.quantity_available = payload.quantity_available

    db.commit()
    db.refresh(stock)
    return stock


# ---- Fulfillment plans ----


class FulfillmentSplitResponse(BaseModel):
    id: int
    quote_line_id: int
    warehouse_id: Optional[int]
    quantity_fulfilled: int
    is_backorder: bool
    warning: Optional[str] = None

    class Config:
        from_attributes = True


class FulfillmentPlanResponse(BaseModel):
    id: int
    quote_id: int
    status: str
    splits: List[FulfillmentSplitResponse]
    backorder_summary: List[str] = []

    class Config:
        from_attributes = True


def _load_stock_by_product(db: Session, product_ids: List[int]) -> Dict[int, List[WarehouseStockInput]]:
    if not product_ids:
        return {}

    rows = (
        db.query(Stock, Warehouse)
        .join(Warehouse, Stock.warehouse_id == Warehouse.id)
        .filter(Stock.product_id.in_(product_ids))
        .all()
    )

    stock_by_product: Dict[int, List[WarehouseStockInput]] = {}
    for stock, warehouse in rows:
        stock_by_product.setdefault(stock.product_id, []).append(
            WarehouseStockInput(
                warehouse_id=warehouse.id,
                shipping_cost_weight=warehouse.shipping_cost_weight,
                quantity_available=stock.quantity_available,
            )
        )
    return stock_by_product


def _backorder_summary_for_plan(plan: FulfillmentPlan, db: Session) -> List[str]:
    summary = []
    for split in plan.splits:
        if not split.is_backorder:
            continue
        quote_line = db.get(QuoteLine, split.quote_line_id)
        summary.append(
            f"Line {split.quote_line_id} (Product {quote_line.product_id}): "
            f"{split.quantity_fulfilled} of {quote_line.quantity} units backordered"
        )
    return summary


def _get_latest_plan_or_404(quote_id: int, db: Session) -> FulfillmentPlan:
    plan = (
        db.query(FulfillmentPlan)
        .filter(FulfillmentPlan.quote_id == quote_id)
        .order_by(FulfillmentPlan.id.desc())
        .first()
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="No fulfillment plan found for this quote")
    return plan


@router.post("/quotes/{quote_id}/fulfillment/suggest", response_model=FulfillmentPlanResponse)
def suggest_fulfillment(quote_id: int, db: Session = Depends(get_db)):
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.status != QuoteStatus.approved:
        raise HTTPException(
            status_code=400, detail="Quote must be approved before fulfillment can be suggested"
        )

    lines = build_fulfillment_lines(quote_id, db)
    stock_by_product = _load_stock_by_product(db, [line.product_id for line in lines])
    result = plan_fulfillment(lines, stock_by_product)

    # A quote can be re-suggested (e.g. after stock changes); replace any
    # prior suggestion rather than accumulating stale ones.
    existing = (
        db.query(FulfillmentPlan)
        .filter(FulfillmentPlan.quote_id == quote_id, FulfillmentPlan.status == FulfillmentPlanStatus.suggested)
        .first()
    )
    if existing is not None:
        db.delete(existing)
        db.flush()

    plan = FulfillmentPlan(quote_id=quote_id, status=FulfillmentPlanStatus.suggested)
    db.add(plan)
    db.flush()

    for allocation in result.allocations:
        db.add(
            FulfillmentSplit(
                fulfillment_plan_id=plan.id,
                quote_line_id=allocation.quote_line_id,
                warehouse_id=allocation.warehouse_id,
                quantity_fulfilled=allocation.quantity_fulfilled,
                is_backorder=allocation.is_backorder,
            )
        )

    db.commit()
    db.refresh(plan)

    response = FulfillmentPlanResponse.model_validate(plan)
    response.backorder_summary = result.backorder_summary
    return response


@router.post("/quotes/{quote_id}/fulfillment/confirm", response_model=FulfillmentPlanResponse)
def confirm_fulfillment(quote_id: int, db: Session = Depends(get_db)):
    plan = (
        db.query(FulfillmentPlan)
        .filter(FulfillmentPlan.quote_id == quote_id, FulfillmentPlan.status == FulfillmentPlanStatus.suggested)
        .first()
    )
    if plan is None:
        raise HTTPException(status_code=400, detail="No suggested fulfillment plan exists for this quote")

    shippable_splits = [s for s in plan.splits if not s.is_backorder]

    # Lock and total up the stock rows this confirmation needs, without
    # mutating anything yet, so a shortage can be reported cleanly.
    needed_by_stock_id: Dict[int, int] = {}
    stock_rows: Dict[int, Stock] = {}
    shortages: List[str] = []

    for split in shippable_splits:
        quote_line = db.get(QuoteLine, split.quote_line_id)
        stock = (
            db.query(Stock)
            .filter(Stock.warehouse_id == split.warehouse_id, Stock.product_id == quote_line.product_id)
            .with_for_update()
            .first()
        )
        if stock is None:
            shortages.append(
                f"Line {split.quote_line_id}: no stock record for product {quote_line.product_id} "
                f"at warehouse {split.warehouse_id}"
            )
            continue
        needed_by_stock_id[stock.id] = needed_by_stock_id.get(stock.id, 0) + split.quantity_fulfilled
        stock_rows[stock.id] = stock

    for stock_id, needed in needed_by_stock_id.items():
        stock = stock_rows[stock_id]
        if stock.quantity_available < needed:
            shortages.append(
                f"Warehouse {stock.warehouse_id}/product {stock.product_id}: "
                f"needs {needed} but only {stock.quantity_available} available"
            )

    if shortages:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Stock insufficient to confirm fulfillment: {'; '.join(shortages)}",
        )

    for stock_id, needed in needed_by_stock_id.items():
        stock_rows[stock_id].quantity_available -= needed

    plan.status = FulfillmentPlanStatus.confirmed

    shipment_count = len({s.warehouse_id for s in shippable_splits})
    backorder_count = len(plan.splits) - len(shippable_splits)
    db.add(
        AuditLog(
            quote_id=quote_id,
            user="system",
            action="fulfillment_confirmed",
            reason=f"{shipment_count} shipment(s) confirmed; {backorder_count} line(s) backordered.",
        )
    )

    db.commit()
    db.refresh(plan)

    response = FulfillmentPlanResponse.model_validate(plan)
    response.backorder_summary = _backorder_summary_for_plan(plan, db)
    return response


class OverrideAllocation(BaseModel):
    quote_line_id: int
    warehouse_id: int
    quantity_fulfilled: int


class OverrideRequest(BaseModel):
    allocations: List[OverrideAllocation]


@router.patch("/quotes/{quote_id}/fulfillment/override", response_model=FulfillmentPlanResponse)
def override_fulfillment(quote_id: int, payload: OverrideRequest, db: Session = Depends(get_db)):
    plan = _get_latest_plan_or_404(quote_id, db)

    quote_lines = {
        line.id: line for line in db.query(QuoteLine).filter(QuoteLine.quote_id == quote_id).all()
    }

    # A full replacement must cover every line's quantity_needed exactly.
    totals_by_line: Dict[int, int] = {}
    for allocation in payload.allocations:
        totals_by_line[allocation.quote_line_id] = (
            totals_by_line.get(allocation.quote_line_id, 0) + allocation.quantity_fulfilled
        )

    mismatches: List[str] = []
    for line_id, quote_line in quote_lines.items():
        provided = totals_by_line.get(line_id, 0)
        if provided != quote_line.quantity:
            mismatches.append(
                f"Line {line_id}: allocations sum to {provided} but {quote_line.quantity} units are needed"
            )
    for line_id in set(totals_by_line) - set(quote_lines):
        mismatches.append(f"Line {line_id} does not belong to quote {quote_id}")

    if mismatches:
        raise HTTPException(
            status_code=400,
            detail=f"Allocation quantities do not match line requirements: {'; '.join(mismatches)}",
        )

    db.query(FulfillmentSplit).filter(FulfillmentSplit.fulfillment_plan_id == plan.id).delete(
        synchronize_session=False
    )

    for allocation in payload.allocations:
        db.add(
            FulfillmentSplit(
                fulfillment_plan_id=plan.id,
                quote_line_id=allocation.quote_line_id,
                warehouse_id=allocation.warehouse_id,
                quantity_fulfilled=allocation.quantity_fulfilled,
                is_backorder=False,
            )
        )

    plan.status = FulfillmentPlanStatus.manually_overridden
    db.add(
        AuditLog(
            quote_id=quote_id,
            user="system",
            action="fulfillment_overridden",
            reason="Manually overridden by rep/ops user",
        )
    )

    db.commit()
    db.refresh(plan)

    # Flag (without blocking) allocations that exceed currently known stock -
    # a human is knowingly overriding the suggestion, so this warns rather
    # than rejects.
    warehouse_ids = {a.warehouse_id for a in payload.allocations}
    stock_lookup = {
        (s.warehouse_id, s.product_id): s.quantity_available
        for s in db.query(Stock).filter(Stock.warehouse_id.in_(warehouse_ids)).all()
    }

    response = FulfillmentPlanResponse.model_validate(plan)
    for split_response in response.splits:
        quote_line = quote_lines[split_response.quote_line_id]
        available = stock_lookup.get((split_response.warehouse_id, quote_line.product_id))
        if available is not None and split_response.quantity_fulfilled > available:
            split_response.warning = (
                f"Requested {split_response.quantity_fulfilled} exceeds known available stock "
                f"({available}) at warehouse {split_response.warehouse_id}"
            )

    return response


@router.get("/quotes/{quote_id}/fulfillment", response_model=FulfillmentPlanResponse)
def get_fulfillment(quote_id: int, db: Session = Depends(get_db)):
    plan = _get_latest_plan_or_404(quote_id, db)

    response = FulfillmentPlanResponse.model_validate(plan)
    response.backorder_summary = _backorder_summary_for_plan(plan, db)
    return response
