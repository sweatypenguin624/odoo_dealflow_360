# 25. Question & Answer Guide

This section is designed to quickly answer common questions about the DealFlow360 architecture and codebase.

### Architecture
**Q: Why is the project structured this way?**
A: DealFlow360 uses a Hexagonal / Service-Layer architecture. The FastAPI routers (`app/routers/`) are decoupled from the business logic (`app/services/`). This ensures the logic can be unit-tested without a database and prevents API files from becoming massive "fat controllers".

**Q: What are the major components?**
A: 
1. **API Routers**: FastAPI endpoints receiving JSON.
2. **Database Models**: SQLAlchemy classes mapping to SQLite tables.
3. **Core Engines**: Pure Python classes handling Risk, Fulfillment, Billing, and Upsell logic.
4. **ML Pipeline**: Offline scripts (`upsell_cross_sell/`) that train an XGBoost model.

### Code
**Q: What does `evaluate_quote()` do?**
A: It iterates through a quote's lines, compares requested discounts against maximum allowable category/tier limits, tallies "points over", and returns whether the quote can be auto-approved, or if it requires manager/finance approval.

**Q: Where is the XGBoost prediction logic implemented?**
A: The actual training happens in `upsell_cross_sell/ml/train_model.py`. The real-time inference happens inside `app/services/upsell_engine.py` using the pre-trained `recommendation_model.json`.

**Q: Where would I make a change if I want to add a "Platinum" tier?**
A: You would add a row to the `customer_tiers` database table. The code dynamically reads tier limits from the DB, so no code changes in `risk_engine.py` are required.

### Data
**Q: Where does the ML training data come from?**
A: Offline CSVs stored in `upsell_cross_sell/data/` (e.g., `invoices.csv`, `customers.csv`). `build_training_data.py` processes these into `ml_training.csv`.

**Q: How does a QuoteLine turn into a Subscription?**
A: When a user calls `POST /quotes/{id}/lines/{line_id}/subscribe`, the `billing.py` router reads the QuoteLine, instantiates a `Subscription` model, sets `is_recurring=True` on the QuoteLine, and generates an initial `BillingEvent` (invoice).

### Debugging
**Q: If stock isn't decrementing during fulfillment, where should I look?**
A: Look at `app/routers/fulfillment.py`, specifically the `confirm_fulfillment` endpoint. Check if the `.with_for_update()` lock is working, and ensure the loop is correctly subtracting from `quantity_available` before `db.commit()`.

**Q: What dependencies could cause the ML pipeline to fail?**
A: `xgboost` relying on CUDA. If you run `train_model.py` on a Mac or a machine without an Nvidia GPU, the CUDA drivers will fail. The script has a fallback to `cpu`, but if that fails, you need to verify the `xgboost` installation.
