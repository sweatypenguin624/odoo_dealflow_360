# 23. Non-Obvious Behavior and Edge Cases

This section documents "gotchas" and implicit behaviors that could easily confuse a new developer.

## 1. Fulfillment Suggestion Clobbering
In `fulfillment.py` -> `suggest_fulfillment()`, if a `suggested` plan already exists for a quote, the system actively deletes it (`db.delete(existing)`) before creating the new one. This is intentional. Because warehouse stock fluctuates constantly, a saved suggestion from yesterday might be impossible today. Forcing the system to clobber old suggestions prevents stale stock assumptions.

## 2. Row-Level Locking in Fulfillment
In `confirm_fulfillment`, you will see `db.query(Stock)...with_for_update()`. This is absolutely critical. Without it, two simultaneous users confirming two different quotes could both see "10 laptops available" and both successfully confirm, leaving the warehouse with -10 laptops. `.with_for_update()` forces the database to lock those specific product rows until the transaction commits.

## 3. The `quote_loader.py` Translation Layer
A developer might wonder why routers don't just pass SQLAlchemy models (like `QuoteLine`) directly into the Engines. The codebase explicitly converts them to Dataclasses (`LineInput`, `LineToFulfill`) via `quote_loader.py` first. This is an intentional architectural pattern to prevent the Engines from triggering "Lazy Loading" queries by accident (e.g., if the engine typed `line.product.category.name`, SQLAlchemy would implicitly run a database query behind the scenes). Dataclasses ensure all DB interaction stays in the router layer.

## 4. Proration Day Math Floor
In `billing_engine.py`, the calculation for `days_remaining` uses `max(0, (cycle_end - as_of).days)`. If a user downgrades a subscription *after* their billing cycle has ended (but before the system processed the renewal), the system floors the days at 0, meaning they get $0 in credit.

## 5. Model Loading at Import
In `upsell_engine.py` (and the ML modules), the XGBoost model is loaded into memory when the Python module is imported. This means if the `train_model.py` script replaces `recommendation_model.json` on disk, the FastAPI server **must be restarted** for the changes to take effect. It does not hot-reload the model.
