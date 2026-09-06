"""Inventory state transitions.

on_hand   - physical units in the warehouse
reserved  - units promised to confirmed fulfillment plans but not yet shipped
available - on_hand - reserved (what a new plan may take)

Every change writes an InventoryMovement, and every reserve/consume
locks the stock row (SELECT ... FOR UPDATE on PostgreSQL) and re-checks
the quantity inside the same transaction, so two orders can never both
take the last units.
"""

from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models import InventoryMovement, MovementType, Product, Stock, User, Warehouse
from app.services import audit_service


class StockShortage(ConflictError):
    code = "stock_shortage"


def get_stock(db: Session, warehouse_id: int, product_id: int, *, for_update: bool = False, create: bool = False) -> Optional[Stock]:
    query = db.query(Stock).filter(Stock.warehouse_id == warehouse_id, Stock.product_id == product_id)
    if for_update:
        query = query.with_for_update()
    stock = query.first()
    if stock is None and create:
        if db.get(Warehouse, warehouse_id) is None:
            raise NotFoundError("Warehouse not found")
        if db.get(Product, product_id) is None:
            raise NotFoundError("Product not found")
        stock = Stock(warehouse_id=warehouse_id, product_id=product_id, quantity_on_hand=0, quantity_reserved=0)
        db.add(stock)
        db.flush()
    return stock


def _movement(db: Session, stock: Stock, movement_type: MovementType, quantity: int, reference_type, reference_id, actor: Optional[User], note: Optional[str]) -> InventoryMovement:
    movement = InventoryMovement(
        stock_id=stock.id,
        warehouse_id=stock.warehouse_id,
        product_id=stock.product_id,
        movement_type=movement_type,
        quantity=quantity,
        on_hand_after=stock.quantity_on_hand,
        reserved_after=stock.quantity_reserved,
        reference_type=reference_type,
        reference_id=reference_id,
        actor_user_id=actor.id if actor else None,
        note=note,
    )
    db.add(movement)
    return movement


def receive(db: Session, warehouse_id: int, product_id: int, quantity: int, actor: Optional[User], note: Optional[str] = None, reference_type: str = "receipt", reference_id: Optional[int] = None) -> Stock:
    if quantity <= 0:
        raise ValidationError("Receipt quantity must be positive.")
    stock = get_stock(db, warehouse_id, product_id, for_update=True, create=True)
    stock.quantity_on_hand += quantity
    _movement(db, stock, MovementType.receipt, quantity, reference_type, reference_id, actor, note)
    audit_service.record(db, "stock_received", actor=actor, entity_type="stock", entity_id=stock.id, after={"warehouse_id": warehouse_id, "product_id": product_id, "quantity": quantity, "on_hand": stock.quantity_on_hand}, reason=note)
    return stock


def adjust(db: Session, warehouse_id: int, product_id: int, new_on_hand: int, actor: Optional[User], reason: str) -> Stock:
    if new_on_hand < 0:
        raise ValidationError("On-hand quantity cannot be negative.")
    if not reason or not reason.strip():
        raise ValidationError("An adjustment reason is required.")
    stock = get_stock(db, warehouse_id, product_id, for_update=True, create=True)
    if new_on_hand < stock.quantity_reserved:
        raise ConflictError(f"Cannot set on-hand below the {stock.quantity_reserved} units currently reserved.")
    delta = new_on_hand - stock.quantity_on_hand
    before = stock.quantity_on_hand
    stock.quantity_on_hand = new_on_hand
    _movement(db, stock, MovementType.adjustment, delta, "adjustment", None, actor, reason)
    audit_service.record(db, "stock_adjusted", actor=actor, entity_type="stock", entity_id=stock.id, before={"on_hand": before}, after={"on_hand": new_on_hand}, reason=reason)
    return stock


def reserve(db: Session, warehouse_id: int, product_id: int, quantity: int, reference_type: str, reference_id: int, actor: Optional[User]) -> Stock:
    stock = get_stock(db, warehouse_id, product_id, for_update=True)
    if stock is None:
        raise StockShortage(f"No stock record for product {product_id} at warehouse {warehouse_id}")
    if stock.quantity_available < quantity:
        raise StockShortage(
            f"Warehouse {stock.warehouse.name}/{stock.product.name}: needs {quantity} but only {stock.quantity_available} available"
        )
    stock.quantity_reserved += quantity
    _movement(db, stock, MovementType.reservation, quantity, reference_type, reference_id, actor, None)
    return stock


def release(db: Session, warehouse_id: int, product_id: int, quantity: int, reference_type: str, reference_id: int, actor: Optional[User]) -> Stock:
    stock = get_stock(db, warehouse_id, product_id, for_update=True)
    if stock is None:
        return None
    stock.quantity_reserved = max(0, stock.quantity_reserved - quantity)
    _movement(db, stock, MovementType.release, quantity, reference_type, reference_id, actor, None)
    return stock


def consume(db: Session, warehouse_id: int, product_id: int, quantity: int, reference_type: str, reference_id: int, actor: Optional[User]) -> Stock:
    """Ship reserved units: they leave both on_hand and reserved."""
    stock = get_stock(db, warehouse_id, product_id, for_update=True)
    if stock is None or stock.quantity_on_hand < quantity:
        raise StockShortage(f"Cannot ship {quantity} units of product {product_id} from warehouse {warehouse_id}: insufficient on-hand stock")
    stock.quantity_on_hand -= quantity
    stock.quantity_reserved = max(0, stock.quantity_reserved - quantity)
    _movement(db, stock, MovementType.consumption, quantity, reference_type, reference_id, actor, None)
    return stock


def available_by_product(db: Session, product_ids: List[int]) -> Dict[int, int]:
    if not product_ids:
        return {}
    rows = (
        db.query(Stock.product_id, func.coalesce(func.sum(Stock.quantity_on_hand - Stock.quantity_reserved), 0))
        .filter(Stock.product_id.in_(product_ids))
        .group_by(Stock.product_id)
        .all()
    )
    return {pid: int(qty) for pid, qty in rows}
