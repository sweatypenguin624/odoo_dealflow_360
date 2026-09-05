# 8. Database Architecture

DealFlow360 utilizes a relational database mapped via SQLAlchemy. The models are highly normalized to ensure data integrity across quotes, fulfillment, billing, and ML tracking.

## Core Schema Structure

### Customer Domain
- **`customer_tiers`**: Defines tiers (Silver, Gold) and their `max_discount_pct`.
- **`customers`**: Links a business entity to a `tier_id`.

### Catalog Domain
- **`categories`**: Groupings for products, overriding discount logic.
- **`products`**: Defines `price`, `unit_margin_pct`, and links to a `category_id`.
- **`product_pairings`**: (Populated by ML Apriori) Stores `co_purchase_score` between a `base_product_id` and a `suggested_product_id`.

### Quote Domain
- **`quotes`**: The parent container for a deal. Tracks `status` (draft, pending_approval, approved, etc.) and `current_approval_step`.
- **`quote_lines`**: Child items of a quote. Stores `product_id`, `quantity`, `discount_pct`, `line_value`, and a boolean `is_recurring`.
- **`approval_actions`**: A historical ledger of who approved/rejected what, when, and why.
- **`audit_logs`**: A system-level ledger tracking automated state changes (e.g., auto-approved, fulfillment confirmed).

### Fulfillment Domain
- **`warehouses`**: Physical locations with a `shipping_cost_weight` metric.
- **`stock`**: The junction table between `warehouses` and `products`, tracking `quantity_available`.
- **`fulfillment_plans`**: Linked to an approved `quote`. Tracks the overall shipping `status` (suggested, confirmed, manually_overridden).
- **`fulfillment_splits`**: Child records mapping a `quote_line_id` to a `warehouse_id`, detailing `quantity_fulfilled` and if it `is_backorder`.

### Billing Domain
- **`subscription_plans`**: Defines recurring templates (e.g., `interval` = monthly, `price_per_interval`).
- **`subscriptions`**: The active contract resulting from an approved recurring `quote_line`. Tracks `status`, `quantity`, and cycle dates.
- **`billing_events`**: An immutable ledger of financial impacts (e.g., `invoice`, `proration_charge`, `refund`, `cancellation_credit`) linked to a subscription.

## Migrations (Alembic)
The database schema is entirely controlled by Alembic (found in `backend/alembic/versions/`).
When the SQLAlchemy models in `app/models/` are modified, a developer runs `alembic revision --autogenerate -m "description"` to generate a script, followed by `alembic upgrade head` to apply it. The presence of SQLite indicates a local dev environment, but the strict SQLAlchemy mapping ensures production compatibility with PostgreSQL.
