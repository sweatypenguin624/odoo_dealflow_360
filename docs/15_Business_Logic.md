# 15. Business Logic Summary

This section strips away the technical implementation and explains the pure business rules that DealFlow360 enforces.

## 1. Quoting and Discounts
- **Rule**: Every customer belongs to a Tier (e.g., "Silver", "Gold") which grants them a maximum allowable discount percentage.
- **Rule**: Products belong to a Category. A Category can optionally have its own maximum discount limit.
- **Rule**: If a Category has a limit, it *overrides* the Customer Tier limit for that specific line item. If the Category has no limit, the Tier limit applies.
- **Rule**: The system calculates "Points Over" for every line. If a line has a 12% discount, but its limit is 10%, it is 2 points over.
- **Approval Thresholds**:
  - If the sum of all "Points Over" across the quote >= 15, or any single line is >= 15 points over, the quote requires **Manager AND Finance** approval.
  - If the sum is >= 5, or a single line is >= 5 points over, it requires **Manager** approval.
  - Otherwise, it is auto-approved.

## 2. Order Fulfillment
- **Rule**: An order cannot be fulfilled until the Quote is strictly `approved`.
- **Rule**: Warehouses are prioritized by their `shipping_cost_weight` (cheapest first).
- **Rule**: If two warehouses have the same shipping cost, the one with the *most* available stock is used to prevent fragmenting orders across many boxes.
- **Rule**: The system will exhaust a warehouse's stock before splitting the remaining quantity to the next cheapest warehouse.
- **Rule**: If all warehouse stock is exhausted and the line is still not fulfilled, the remainder is marked as a Backorder.

## 3. Subscription Billing
- **Rule**: Proration only applies if a seat quantity is changed *before* the current billing cycle ends.
- **Rule**: If a customer reduces their seat count mid-cycle, they receive a prorated credit for the unused days. If they increase it, they receive a prorated charge.
- **Rule**: If a subscription is cancelled mid-cycle, the customer is immediately refunded/credited for the unused days.

## 4. Upsell Machine Learning
- **Rule**: The system will *never* recommend an upsell product if its `unit_margin_pct` is below the configured threshold (default 10%). Profitability overrides prediction probability.
- **Rule**: Items manually flagged by admins as `is_promoted = True` will *always* sort above unpromoted items, regardless of how highly the ML algorithm scores them.
