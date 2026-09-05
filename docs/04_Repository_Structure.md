# 4. Repository Structure

This section explains what each directory and important file in the project is responsible for and how it fits into the overall architecture.

```text
odoo_dealflow_360/
├── backend/                  # The core FastAPI application and ML Pipeline
│   ├── alembic/              # Database migration scripts
│   ├── app/                  # The actual API source code
│   ├── tests/                # Pytest suite
│   ├── upsell_cross_sell/    # ML pipeline for recommendations
│   └── requirements.txt      # Python dependencies
├── frontend/                 # Next.js web application
│   ├── app/                  # Next.js App Router (Pages, Layouts)
│   ├── public/               # Static assets
│   └── package.json          # Node dependencies
└── docs/                     # This documentation
```

## `backend/app/` (The Core API)

This directory houses the web server and business logic.

- **`main.py`**: The entry point for the FastAPI application. It initializes the app, registers the routers, and sets up health checks.
- **`config.py`**: Handles environment variables (e.g., database URLs) using `pydantic-settings`. It ensures the app won't boot if critical config is missing.
- **`database.py`**: Sets up the SQLAlchemy engine and the `SessionLocal` factory used to interact with the database.

### `backend/app/models/`
Contains the SQLAlchemy ORM models mapping Python classes to database tables.
- **`customer.py`**: Defines `Customer` and `CustomerTier` tables.
- **`quote.py`**: Defines `Quote`, `QuoteLine`, and statuses. Central to the DealFlow.
- **`fulfillment.py`**: Defines `FulfillmentPlan` and `FulfillmentSplit`.
- **`subscription.py` & `subscription_plan.py`**: Defines recurring revenue models.
- **`approval.py` & `audit.py`**: Handles risk tracking and audit logs.
- **`product.py` & `warehouse.py`**: Defines catalog and stock.

### `backend/app/routers/`
The HTTP interface. Files here (e.g., `quotes.py`, `billing.py`, `fulfillment.py`) define the API endpoints (`@app.post()`, `@app.get()`), parse Pydantic schemas, and immediately hand off execution to the `services`.

### `backend/app/services/`
The "Engines". This is where the actual business logic lives.
- **`risk_engine.py`**: Evaluates if a quote is safe to approve.
- **`billing_engine.py`**: Translates quotes into subscriptions.
- **`fulfillment_engine.py`**: Calculates warehouse routing.
- **`upsell_engine.py`**: Generates product recommendations.

## `backend/alembic/` (Migrations)
- **`env.py`**: Alembic configuration that imports the SQLAlchemy `Base` so it can auto-generate migrations by comparing code to the DB.
- **`versions/`**: Contains sequential Python scripts that alter the database schema (e.g., `42f08f46c319_initial_models.py`).

## `backend/upsell_cross_sell/` (The ML Pipeline)
A standalone python module responsible for training the XGBoost model.
- **`data/`**: Contains raw CSVs (`invoices.csv`, `customers.csv`) used to train the model.
- **`ml/build_training_data.py`**: A complex script that iterates chronologically through invoices, calculates historical user state, generates positive/negative cross-sell/upsell examples, and outputs `ml_training.csv`.
- **`ml/train_model.py`**: Loads the training CSV, trains an XGBoost Classifier (`xgb.XGBClassifier`), and saves the binary model to disk.
- **`models/`**: The output directory containing `recommendation_model.json` and `feature_columns.json`, which are later read by `backend/app/services/upsell_engine.py`.
- **`cross_sell/` & `upsell/`**: Contains Apriori rule generation logic.

## `frontend/` (The User Interface)
Standard Next.js 16 setup using the App Router.
- **`app/page.tsx`**: The main landing page.
- **`app/layout.tsx`**: The root HTML shell and global providers.
- **`tailwind.config.js` / `globals.css`**: Styling configurations.
