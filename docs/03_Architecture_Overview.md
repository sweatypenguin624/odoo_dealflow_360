# 3. Architecture Overview

DealFlow360 uses a monolithic, module-driven backend architecture with a separated machine learning pipeline. While the API and logic live in a single repository (`backend/`), the responsibilities are strictly separated by domain boundaries (Quotes, Billing, Fulfillment, Risk, Upsell).

## The Major Components

1. **The API Layer (`app.routers`)**: 
   - Exposes RESTful endpoints for the client (Next.js frontend).
   - Responsible strictly for receiving HTTP requests, validating them via Pydantic, invoking the underlying domain engines, and formatting the response.

2. **The Domain Engines (`app.services`)**:
   - The absolute core of the application. Business logic does not live in routers; it lives in "Engines."
   - **Quote Loader**: Ingests deals/quotes.
   - **Risk Engine**: Evaluates quote discounting against customer tiers to auto-approve or block deals.
   - **Fulfillment Engine**: Splits an approved quote into shipments based on warehouse stock availability.
   - **Billing Engine**: Converts quotes into recurring subscriptions or one-time invoices.
   - **Upsell Engine**: Bridges the gap between the transactional database and the ML recommendation system.

3. **The Data Access Layer (`app.models` & `database.py`)**:
   - SQLAlchemy declarative models that define the shape of SQLite/PostgreSQL tables.
   - The engines interact with the database via a shared `SessionLocal` dependency.

4. **The Machine Learning Pipeline (`upsell_cross_sell/`)**:
   - Acts as an asynchronous or offline component. 
   - Ingests raw CSV data (`customers.csv`, `invoices.csv`, etc.).
   - Extracts historical features and trains an XGBoost classifier.
   - Outputs a serialized `recommendation_model.json`.
   - The backend's `Upsell Engine` loads this serialized model at runtime to score real-time deals.

## How the Components Communicate
- **Synchronous HTTP**: The Next.js frontend calls the FastAPI backend.
- **Function Invocation**: Routers instantiate or call Engine classes/functions directly, passing the SQLAlchemy Database Session.
- **File System (ML Interface)**: The ML pipeline communicates with the backend by saving model artifacts (`.json` files) to disk, which the backend reads into memory upon initialization.

## Mental Model of Data Flow
1. **Entry**: Data enters the system when a User submits a Quote payload via `POST /quotes`.
2. **Evaluation**: The Quote is saved to the database. The `Risk Engine` reads it and applies tier-based discount rules.
3. **Augmentation**: The `Upsell Engine` reads the Quote line items and queries the ML model to return recommended additions.
4. **Action**: Once approved, the Quote branches:
   - Tangible goods go to the `Fulfillment Engine` to allocate `Stock`.
   - Recurring goods go to the `Billing Engine` to create `Subscriptions`.
5. **Exit**: The API responds with the augmented quote, or webhooks/events trigger external systems (not yet implemented).
