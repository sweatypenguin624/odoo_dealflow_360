# 11. Core Components Deep Dive

The DealFlow360 backend is built around four central "Engines." These engines are pure Python functions that contain zero FastAPI or Database dependencies, making them highly testable. 

## 1. The Risk Engine (`risk_engine.py`)
**Purpose**: Determines if a quote's discounts are safe or if they require managerial/finance approval.
**How it works**:
- It iterates over every `LineInput` (a quote line translated into a dataclass).
- It compares the line's `discount_pct` against the product category's `max_discount_pct`. If the category has no limit, it falls back to the customer tier's `max_discount_pct`.
- The delta is calculated as `points_over`.
- The engine calculates a `blended_score` (the sum of all `points_over`) and tracks the `worst_points_over` for a single line.
- **Rules**:
  - Max severity >= 15 points: Requires `manager_then_finance` approval.
  - Max severity >= 5 points: Requires `manager` approval.
  - Otherwise: Auto-approved (`none`).

## 2. The Fulfillment Engine (`fulfillment_engine.py`)
**Purpose**: Allocates warehouse stock to physical quote lines to minimize shipments.
**How it works**:
- Receives a list of `LineToFulfill` and a dictionary of available `WarehouseStockInput`s.
- It sorts warehouses by `shipping_cost_weight` ascending, using `quantity_available` descending as a tie-breaker (to drain heavily stocked warehouses first).
- It greedily drains stock from the cheapest warehouse for a product. If that warehouse is depleted, it moves to the next cheapest.
- Any remaining unfulfilled quantity is flagged as a `backorder` (no warehouse ID).
- Stock counts are decremented *in memory* during the loop to ensure lines sharing the same product don't double-dip.

## 3. The Billing Engine (`billing_engine.py`)
**Purpose**: Handles the math for prorations and subscription cancellations.
**How it works**:
- Relies heavily on exact day math using `(cycle_end - cycle_start).days`.
- **Proration**: When quantity changes mid-cycle, it calculates the daily rate of the old quantity and the new quantity. It multiplies the rate delta by the `days_remaining_in_cycle`. A positive number is a charge; negative is a credit.
- **Cancellation**: Refunds the remainder of the cycle by multiplying the current daily rate by `days_remaining_in_cycle`.

## 4. The Upsell Engine (`upsell_engine.py`)
**Purpose**: Ranks machine-learning suggestions against a live quote to maximize margin.
**How it works**:
- Calculates the baseline `overall_margin_pct` of the current quote.
- Filters out candidates below a strict `min_margin_pct_threshold`.
- Sorts remaining candidates first by `is_promoted` (True > False), then by ML `co_purchase_score` (descending).
- For each candidate, it simulates appending it to the quote at 0% discount and recalculates the margin, outputting `margin_delta_if_added` so the UI can display the impact.
