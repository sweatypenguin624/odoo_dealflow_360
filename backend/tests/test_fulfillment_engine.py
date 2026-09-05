from app.services.fulfillment_engine import (
    LineToFulfill,
    WarehouseStockInput,
    plan_fulfillment,
)


def test_single_line_single_warehouse_has_enough_stock():
    lines = [LineToFulfill(quote_line_id=1, product_id=10, quantity_needed=5)]
    stock_by_product = {
        10: [WarehouseStockInput(warehouse_id=100, shipping_cost_weight=1.0, quantity_available=20)],
    }

    result = plan_fulfillment(lines, stock_by_product)

    assert len(result.allocations) == 1
    allocation = result.allocations[0]
    assert allocation.quote_line_id == 1
    assert allocation.warehouse_id == 100
    assert allocation.quantity_fulfilled == 5
    assert allocation.is_backorder is False
    assert result.total_shipments == 1
    assert result.has_backorder is False
    assert result.backorder_summary == []


def test_single_line_splits_across_two_warehouses():
    lines = [LineToFulfill(quote_line_id=1, product_id=10, quantity_needed=15)]
    stock_by_product = {
        10: [
            WarehouseStockInput(warehouse_id=100, shipping_cost_weight=1.0, quantity_available=10),
            WarehouseStockInput(warehouse_id=200, shipping_cost_weight=2.0, quantity_available=10),
        ],
    }

    result = plan_fulfillment(lines, stock_by_product)

    assert result.total_shipments == 2
    assert len(result.allocations) == 2
    assert sum(a.quantity_fulfilled for a in result.allocations) == 15
    assert {a.warehouse_id for a in result.allocations} == {100, 200}
    # Cheapest warehouse (100) should be drained first.
    assert result.allocations[0].warehouse_id == 100
    assert result.allocations[0].quantity_fulfilled == 10
    assert result.allocations[1].warehouse_id == 200
    assert result.allocations[1].quantity_fulfilled == 5
    assert result.has_backorder is False


def test_quantity_exceeding_total_stock_creates_backorder():
    lines = [LineToFulfill(quote_line_id=3, product_id=10, quantity_needed=20)]
    stock_by_product = {
        10: [WarehouseStockInput(warehouse_id=100, shipping_cost_weight=1.0, quantity_available=8)],
    }

    result = plan_fulfillment(lines, stock_by_product)

    assert result.has_backorder is True
    backorder_allocations = [a for a in result.allocations if a.is_backorder]
    assert len(backorder_allocations) == 1
    assert backorder_allocations[0].warehouse_id is None
    assert backorder_allocations[0].quantity_fulfilled == 12
    assert len(result.backorder_summary) == 1
    assert "Line 3" in result.backorder_summary[0]
    assert "12 of 20 units backordered" in result.backorder_summary[0]


def test_multiple_lines_from_same_warehouse_count_as_one_shipment():
    lines = [
        LineToFulfill(quote_line_id=1, product_id=10, quantity_needed=5),
        LineToFulfill(quote_line_id=2, product_id=20, quantity_needed=5),
    ]
    stock_by_product = {
        10: [WarehouseStockInput(warehouse_id=100, shipping_cost_weight=1.0, quantity_available=10)],
        20: [WarehouseStockInput(warehouse_id=100, shipping_cost_weight=1.0, quantity_available=10)],
    }

    result = plan_fulfillment(lines, stock_by_product)

    assert result.total_shipments == 1
    assert len(result.allocations) == 2
    assert all(a.warehouse_id == 100 for a in result.allocations)
    assert result.has_backorder is False


def test_ties_in_shipping_cost_prefer_more_available_stock():
    lines = [LineToFulfill(quote_line_id=1, product_id=10, quantity_needed=10)]
    stock_by_product = {
        10: [
            WarehouseStockInput(warehouse_id=100, shipping_cost_weight=1.0, quantity_available=5),
            WarehouseStockInput(warehouse_id=200, shipping_cost_weight=1.0, quantity_available=50),
        ],
    }

    result = plan_fulfillment(lines, stock_by_product)

    assert result.total_shipments == 1
    assert len(result.allocations) == 1
    assert result.allocations[0].warehouse_id == 200
    assert result.allocations[0].quantity_fulfilled == 10
