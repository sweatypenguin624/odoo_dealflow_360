# 22. Call Graphs

Visualizing the dependency chains within the backend.

## API Request Call Graph
```text
Client (Next.js)
  │
  ▼
FastAPI Router (e.g., quotes.py)
  │
  ├─► database.py (SessionLocal)
  │     └─► queries app/models/
  │
  ├─► quote_loader.py (Data Translation)
  │     └─► Translates Models to Dataclasses
  │
  └─► Services (e.g., risk_engine.py)
        └─► Pure Python Math / Business Rules
```

## ML Training Call Graph
```text
build_training_data.py
  │
  ├─► Reads CSVs (customers, invoices, products)
  │
  ├─► Calls recommend_upsell() (from upsell/upsell_engine.py)
  │     └─► Apriori Rules filtering
  │
  └─► Writes ml_training.csv

train_model.py
  │
  ├─► Reads ml_training.csv
  │
  ├─► xgboost.XGBClassifier.fit()
  │
  └─► Writes recommendation_model.json
```

## Fulfillment Confirmation Call Graph
```text
POST /quotes/{id}/fulfillment/confirm
  │
  ├─► Query FulfillmentPlan (status == suggested)
  │
  ├─► Iterate Splits:
  │     │
  │     └─► Query Stock .with_for_update() (Row-level Lock)
  │
  ├─► Validate sufficient quantity
  │
  ├─► Decrement Stock quantities
  │
  ├─► Update Plan status -> confirmed
  │
  └─► db.commit() (Releases Locks)
```
