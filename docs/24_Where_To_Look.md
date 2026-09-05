# 24. "Where Do I Look If..." Guide

A quick reference table for navigating the repository when debugging or adding features.

| If I need to understand/modify... | Look here |
| -------------------------- | --------- |
| **Why a quote got rejected/approved** | `app/services/risk_engine.py` |
| **How discounts are applied** | `app/services/risk_engine.py` |
| **Adding a new Quote Status** | `app/models/quote.py` |
| **Modifying the Approval API endpoints** | `app/routers/quotes.py` |
| **How stock is deducted** | `app/routers/fulfillment.py` (look for `confirm_fulfillment`) |
| **How warehouse routing is decided** | `app/services/fulfillment_engine.py` |
| **How proration is calculated mathematically** | `app/services/billing_engine.py` |
| **Adding a new Subscription Billing Event type** | `app/models/subscription.py` |
| **Why an Upsell was recommended** | `app/services/upsell_engine.py` |
| **How the ML model is trained** | `upsell_cross_sell/ml/train_model.py` |
| **How the ML training dataset is built** | `upsell_cross_sell/ml/build_training_data.py` |
| **Adding a new environment variable** | `app/config.py` |
| **Modifying database tables (SQL)** | Update models in `app/models/`, then run Alembic. |
| **Database connection issues** | `app/database.py` |
| **FastAPI Startup / Root API issues** | `app/main.py` |
| **Frontend UI / Next.js** | `frontend/app/page.tsx` |
