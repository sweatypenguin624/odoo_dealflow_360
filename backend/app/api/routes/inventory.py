from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_permission
from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import Page, PageParams, paginate_query
from app.core.permissions import Permission
from app.models import InventoryMovement, Product, Stock, User, Warehouse
from app.schemas.inventory import (
    MovementOut,
    StockAdjust,
    StockOut,
    StockReceipt,
    StockUpsert,
    WarehouseCreate,
    WarehouseOut,
    WarehouseUpdate,
)
from app.services import audit_service, inventory_service

router = APIRouter(tags=["inventory"])


def _warehouse_out(w: Warehouse, sku_count: int = 0, units: int = 0) -> WarehouseOut:
    return WarehouseOut.model_validate(w).model_copy(update={"sku_count": sku_count, "units_on_hand": units})


def _stock_out(s: Stock) -> StockOut:
    return StockOut(
        id=s.id, warehouse_id=s.warehouse_id, warehouse_name=s.warehouse.name, product_id=s.product_id, product_name=s.product.name,
        sku=s.product.sku, quantity_on_hand=s.quantity_on_hand, quantity_reserved=s.quantity_reserved, quantity_available=s.quantity_available,
        reorder_point=s.reorder_point, needs_replenishment=s.needs_replenishment, updated_at=s.updated_at,
    )


@router.get("/warehouses", response_model=Page[WarehouseOut])
def list_warehouses(
    params: PageParams = Depends(), include_inactive: bool = False, db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.inventory_read))
):
    query = db.query(Warehouse)
    if not include_inactive:
        query = query.filter(Warehouse.is_active.is_(True))
    rows, total = paginate_query(query.order_by(Warehouse.shipping_cost_weight, Warehouse.name), params)
    stats = {
        wid: (count, units)
        for wid, count, units in db.query(Stock.warehouse_id, func.count(Stock.id), func.coalesce(func.sum(Stock.quantity_on_hand), 0))
        .filter(Stock.warehouse_id.in_([w.id for w in rows] or [0]))
        .group_by(Stock.warehouse_id)
        .all()
    }
    return Page.build([_warehouse_out(w, *stats.get(w.id, (0, 0))) for w in rows], total, params)


@router.post("/warehouses", response_model=WarehouseOut, status_code=201)
def create_warehouse(payload: WarehouseCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.inventory_manage))):
    if payload.code and db.query(Warehouse).filter(Warehouse.code == payload.code).first():
        raise ConflictError(f"Warehouse code {payload.code} is already used.")
    warehouse = Warehouse(**payload.model_dump())
    db.add(warehouse)
    db.flush()
    audit_service.record(db, "warehouse_created", actor=actor, entity_type="warehouse", entity_id=warehouse.id, after=payload.model_dump(mode="json"))
    db.commit()
    return _warehouse_out(warehouse)


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseOut)
def update_warehouse(warehouse_id: int, payload: WarehouseUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.inventory_manage))):
    warehouse = db.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise NotFoundError("Warehouse not found")
    data = payload.model_dump(exclude_unset=True)
    if "code" in data and data["code"] and db.query(Warehouse).filter(Warehouse.code == data["code"], Warehouse.id != warehouse.id).first():
        raise ConflictError(f"Warehouse code {data['code']} is already used.")
    for key, value in data.items():
        setattr(warehouse, key, value)
    audit_service.record(db, "warehouse_updated", actor=actor, entity_type="warehouse", entity_id=warehouse.id, after=payload.model_dump(mode="json", exclude_unset=True))
    db.commit()
    return _warehouse_out(warehouse)


@router.get("/inventory", response_model=Page[StockOut])
def list_stock(
    params: PageParams = Depends(),
    q: Optional[str] = Query(None, description="Product name or SKU"),
    warehouse_id: Optional[int] = None,
    product_id: Optional[int] = None,
    low_stock: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.inventory_read)),
):
    query = db.query(Stock).options(joinedload(Stock.warehouse), joinedload(Stock.product)).join(Product, Stock.product_id == Product.id)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if warehouse_id is not None:
        query = query.filter(Stock.warehouse_id == warehouse_id)
    if product_id is not None:
        query = query.filter(Stock.product_id == product_id)
    if low_stock:
        query = query.filter((Stock.quantity_on_hand - Stock.quantity_reserved) <= Stock.reorder_point)
    rows, total = paginate_query(query.order_by(Product.name, Stock.warehouse_id), params)
    return Page.build([_stock_out(s) for s in rows], total, params)


@router.post("/warehouses/{warehouse_id}/receipts", response_model=StockOut, status_code=201, summary="Record incoming stock")
def receive_stock(warehouse_id: int, payload: StockReceipt, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.inventory_manage))):
    stock = inventory_service.receive(db, warehouse_id, payload.product_id, payload.quantity, actor, payload.note)
    db.commit()
    db.refresh(stock)
    return _stock_out(stock)


@router.post("/warehouses/{warehouse_id}/adjustments", response_model=StockOut, summary="Set an absolute on-hand count with a reason")
def adjust_stock(warehouse_id: int, payload: StockAdjust, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.inventory_manage))):
    stock = inventory_service.adjust(db, warehouse_id, payload.product_id, payload.quantity_on_hand, actor, payload.reason)
    if payload.reorder_point is not None:
        stock.reorder_point = payload.reorder_point
    db.commit()
    db.refresh(stock)
    return _stock_out(stock)


@router.post("/warehouses/{warehouse_id}/stock", response_model=StockOut, summary="Legacy: set available stock directly (recorded as an adjustment)")
def upsert_stock(warehouse_id: int, payload: StockUpsert, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.inventory_manage))):
    current = inventory_service.get_stock(db, warehouse_id, payload.product_id, create=True)
    stock = inventory_service.adjust(db, warehouse_id, payload.product_id, payload.quantity_available + current.quantity_reserved, actor, "Stock level set via legacy endpoint")
    db.commit()
    db.refresh(stock)
    return _stock_out(stock)


@router.get("/inventory/movements", response_model=Page[MovementOut])
def list_movements(
    params: PageParams = Depends(), product_id: Optional[int] = None, warehouse_id: Optional[int] = None, movement_type: Optional[str] = None,
    db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.inventory_read)),
):
    query = db.query(InventoryMovement)
    if product_id is not None:
        query = query.filter(InventoryMovement.product_id == product_id)
    if warehouse_id is not None:
        query = query.filter(InventoryMovement.warehouse_id == warehouse_id)
    if movement_type:
        query = query.filter(InventoryMovement.movement_type == movement_type)
    rows, total = paginate_query(query.order_by(InventoryMovement.id.desc()), params)
    products = {p.id: p.name for p in db.query(Product).filter(Product.id.in_({r.product_id for r in rows} or {0})).all()}
    warehouses = {w.id: w.name for w in db.query(Warehouse).filter(Warehouse.id.in_({r.warehouse_id for r in rows} or {0})).all()}
    items = [MovementOut.model_validate(m).model_copy(update={"product_name": products.get(m.product_id, ""), "warehouse_name": warehouses.get(m.warehouse_id, "")}) for m in rows]
    return Page.build(items, total, params)
