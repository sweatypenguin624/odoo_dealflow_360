"""Fulfillment split engine.

Pure Python, no FastAPI or database dependencies, so it can be unit
tested in isolation and reused wherever a quote needs a fulfillment
plan computed (a live "suggest" call, a preview, or a re-plan after
stock changes).

Algorithm (v1, intentionally simple / greedy so it's easy to explain
to judges):
  - For each line, warehouses that stock its product are tried in
    order of shipping_cost_weight ascending (cheapest/preferred
    first). Ties prefer the warehouse with more available stock,
    since that reduces the odds of needing an extra warehouse later.
  - Each warehouse in that order is drained as far as it will go
    before moving to the next, until the line's quantity_needed is
    met.
  - Any remainder after all warehouses are exhausted becomes a single
    backorder allocation (warehouse_id=None).
  - Stock is shared across lines that reference the same product: a
    unit taken by an earlier line is not available to a later one.
  - total_shipments counts distinct warehouses used for fulfilled
    (non-backorder) allocations across the whole order, since the
    goal is to minimize shipments for the order as a whole.

This function never mutates its inputs and never touches a database -
callers own translating the result into persisted rows.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class WarehouseStockInput:
    warehouse_id: int
    shipping_cost_weight: float
    quantity_available: int


@dataclass
class LineToFulfill:
    quote_line_id: int
    product_id: int
    quantity_needed: int


@dataclass
class SplitAllocation:
    quote_line_id: int
    warehouse_id: Optional[int]
    quantity_fulfilled: int
    is_backorder: bool


@dataclass
class FulfillmentResult:
    allocations: List[SplitAllocation]
    total_shipments: int
    has_backorder: bool
    backorder_summary: List[str] = field(default_factory=list)


def _sorted_warehouses(stocks: List[WarehouseStockInput]) -> List[WarehouseStockInput]:
    return sorted(stocks, key=lambda s: (s.shipping_cost_weight, -s.quantity_available))


def _fulfill_line(
    line: LineToFulfill,
    warehouses: List[WarehouseStockInput],
    remaining_stock: Dict[int, int],
) -> List[SplitAllocation]:
    allocations: List[SplitAllocation] = []
    remaining_needed = line.quantity_needed

    for warehouse in warehouses:
        if remaining_needed <= 0:
            break

        available = remaining_stock.get(warehouse.warehouse_id, 0)
        if available <= 0:
            continue

        take = min(remaining_needed, available)
        allocations.append(
            SplitAllocation(
                quote_line_id=line.quote_line_id,
                warehouse_id=warehouse.warehouse_id,
                quantity_fulfilled=take,
                is_backorder=False,
            )
        )
        remaining_stock[warehouse.warehouse_id] -= take
        remaining_needed -= take

    if remaining_needed > 0:
        allocations.append(
            SplitAllocation(
                quote_line_id=line.quote_line_id,
                warehouse_id=None,
                quantity_fulfilled=remaining_needed,
                is_backorder=True,
            )
        )

    return allocations


def plan_fulfillment(
    lines: List[LineToFulfill],
    stock_by_product: Dict[int, List[WarehouseStockInput]],
) -> FulfillmentResult:
    allocations: List[SplitAllocation] = []
    used_warehouses: set = set()
    backorder_summary: List[str] = []

    # One remaining-stock counter per product, shared across every line
    # that needs that product, so units aren't double-allocated.
    remaining_stock_by_product: Dict[int, Dict[int, int]] = {
        product_id: {stock.warehouse_id: stock.quantity_available for stock in stocks}
        for product_id, stocks in stock_by_product.items()
    }
    sorted_warehouses_by_product: Dict[int, List[WarehouseStockInput]] = {
        product_id: _sorted_warehouses(stocks) for product_id, stocks in stock_by_product.items()
    }

    for line in lines:
        warehouses = sorted_warehouses_by_product.get(line.product_id, [])
        remaining_stock = remaining_stock_by_product.setdefault(line.product_id, {})

        line_allocations = _fulfill_line(line, warehouses, remaining_stock)
        allocations.extend(line_allocations)

        for allocation in line_allocations:
            if allocation.is_backorder:
                backorder_summary.append(
                    f"Line {line.quote_line_id} (Product {line.product_id}): "
                    f"{allocation.quantity_fulfilled} of {line.quantity_needed} units backordered"
                )
            else:
                used_warehouses.add(allocation.warehouse_id)

    return FulfillmentResult(
        allocations=allocations,
        total_shipments=len(used_warehouses),
        has_backorder=len(backorder_summary) > 0,
        backorder_summary=backorder_summary,
    )
