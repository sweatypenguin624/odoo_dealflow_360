# 6. Data Flow and Models

DealFlow360 relies heavily on a strictly defined data model. Understanding how data enters, transforms, and is stored is crucial.

## Where Data Originates
Data originates from two primary sources:
1. **User Input**: The Next.js frontend (or API client) sends JSON payloads to the FastAPI endpoints.
2. **Offline Machine Learning Pipeline**: CSV files containing historical `invoices` and `customers` are processed offline to generate `ml_training.csv`, which trains an XGBoost model. The outputs (`recommendation_model.json`, `feature_columns.json`, and `cross_sell_rules.csv`) are then consumed by the backend.

## How Data is Transformed
1. **HTTP Layer to Pydantic**: Incoming JSON is deserialized and strictly validated by Pydantic schemas (e.g., `SubscribeRequest`, `OverrideRequest`).
2. **Pydantic to SQLAlchemy**: Validated Pydantic models are mapped to SQLAlchemy ORM models (e.g., `Quote`, `Subscription`, `FulfillmentPlan`).
3. **SQLAlchemy to Domain Inputs**: Before complex business logic is executed, SQLAlchemy objects are often flattened into plain Python `dataclasses` (e.g., `LineInput` for the Risk Engine, or `WarehouseStockInput` for the Fulfillment Engine). This decouples the core business logic from the database layer, allowing the engines to be easily unit tested without mocking a database.

## Major Domain Entities

### 1. `Customer` & `CustomerTier`
Customers belong to a specific tier (e.g., "Silver", "Gold", "Platinum"). The `tier` dictates their `max_discount_pct`. 

### 2. `Product` & `Category`
Products have a `price` and `unit_margin_pct`. They belong to a `Category`, which can also impose a `max_discount_pct`.

### 3. `Quote` & `QuoteLine` (The Core Nexus)
A deal always starts as a `Quote`. 
- Statuses: `draft` -> `pending_approval` -> `approved` -> `confirmed` -> `rejected`.
- A quote has many `QuoteLines` (which link to a `Product`, `quantity`, and `discount_pct`).
- Once a quote is `approved`, its lines can be fulfilled (if physical) or subscribed to (if recurring).

### 4. `FulfillmentPlan` & `FulfillmentSplit`
If a quote contains physical products, a `FulfillmentPlan` is generated.
- The Engine suggests `FulfillmentSplits` which allocate required quantities against available `Stock` in specific `Warehouse`s.
- Splits can be flagged as `is_backorder=True` if stock is insufficient.

### 5. `Subscription` & `BillingEvent`
If a quote line is recurring, it is converted into a `Subscription`.
- A subscription belongs to a `SubscriptionPlan` (e.g., "Monthly Basic").
- Actions like subscribing, changing quantities, or canceling generate a `BillingEvent` (e.g., `proration_charge`, `cancellation_credit`, `invoice`) to maintain an immutable ledger of financial transactions.

### 6. `ProductPairing`
Populated by the ML Apriori engine, this table stores `co_purchase_score`s between a `base_product_id` and a `suggested_product_id`. The backend uses this data to quickly retrieve candidates before running the XGBoost model in real-time.
