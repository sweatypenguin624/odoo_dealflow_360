# DealFlow360 — Codebase & Architecture Reference Guide

> **Document Purpose**: A comprehensive technical breakdown of every piece of technology, file, and architectural decision in the DealFlow360 repository. This is designed to serve as a deep-dive reference for understanding exactly how the system is built, file by file.

---

## 1. Overall System Architecture

DealFlow360 is a quote governance and discount risk evaluation system. It prevents margin leakage by running sales quotes through a mathematical risk engine and routing them for manager or finance approval based on hierarchical rules.

### The Stack
- **Backend**: Python 3.14, FastAPI, SQLAlchemy 2.0, PostgreSQL, Alembic, Pytest.
- **Frontend**: Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4.

### Architectural Philosophy
The backend follows **Clean/Hexagonal Architecture** principles. The core business logic (the mathematical risk engine) is completely isolated from the web framework (FastAPI) and the database (SQLAlchemy). This means the core logic can be tested in milliseconds and reused anywhere without depending on a running database or server.

---

## 2. Backend Directory Breakdown & File Details

### Configuration & Entrypoints

* **`backend/app/main.py`**
  - The entrypoint for the FastAPI application.
  - Initializes the API (`app = FastAPI()`).
  - Registers route modules (e.g., `app.include_router(quotes.router)`).
  - Exposes a simple `GET /health` endpoint for uptime monitoring.

* **`backend/app/config.py`**
  - Uses `pydantic-settings` to load and validate environment variables (like `DATABASE_URL`) from a `.env` file.
  - Provides strict typing for all configuration parameters.

* **`backend/app/database.py`**
  - Configures the SQLAlchemy `engine` using the URL from `config.py`.
  - Configures `SessionLocal`, which is a factory for creating database sessions.
  - Defines the `Base` declarative class that all SQLAlchemy models inherit from.

### Data Models (`backend/app/models/`)

This folder contains the Object-Relational Mapping (ORM) classes that define the database schema and relationships.

* **`__init__.py`**
  - Imports all models so that Alembic migrations can discover them when comparing `Base.metadata` against the actual database schema.

* **`customer.py`**
  - `CustomerTier`: Represents different levels of enterprise relationships (e.g., Gold, Silver). Contains `max_discount_pct` which serves as the baseline discount a customer can receive.
  - `Customer`: Represents a company entity linked to a specific `CustomerTier`.

* **`product.py`**
  - `Category`: Groups products together (e.g., Hardware, Software). Contains an optional `max_discount_pct`. *Business Rule: A category limit overrides a customer tier limit to protect low-margin product lines.*
  - `Product`: Defines an item for sale, its `price`, `unit_margin_pct`, and its parent `Category`.

* **`quote.py`**
  - `Quote`: Represents a financial transaction proposal. Includes foreign key to the `Customer`, a `QuoteStatus` enum (`draft`, `pending_approval`, `approved`, `rejected`, `confirmed`), and fields to track where it is in the approval pipeline (`required_approval_level`, `current_approval_step`, `risk_reasons`).
  - `QuoteLine`: The individual items within a quote. Links to a `Product` and contains `quantity`, `discount_pct`, and the computed `line_value`.

* **`approval.py`**
  - `ApprovalAction`: A structured ledger tracking specific approval decisions in a multi-step chain. Records the `step` (e.g., manager, finance), the `action` (approved, rejected, returned_for_revision), the `actor` (who did it), and optional `reason` notes.

* **`audit.py`**
  - `AuditLog`: An immutable chronological log for compliance tracking. Every time a quote transitions states, an entry is written here (e.g., "quote submitted", "auto-approved", "manager approved").

### Database Migrations (`backend/alembic/`)

* **`alembic/env.py`** & **`alembic.ini`**
  - Configures Alembic to read `DATABASE_URL` from the FastAPI config and hooks it up to the `Base.metadata` from our models.
* **`alembic/versions/`**
  - Contains Python files representing schema diffs (e.g., creating tables, adding columns) generated via `alembic revision --autogenerate`. Running `alembic upgrade head` applies these to the database.

### Core Business Logic (`backend/app/services/`)

* **`risk_engine.py`**
  - The brain of the application. It contains **zero external dependencies**—no FastAPI, no SQLAlchemy.
  - Uses standard Python `dataclasses` (`LineInput`, `LineResult`, `QuoteRiskResult`).
  - **The Math**:
    1. Determines the `applicable_limit` for a line item (uses category limit if present; otherwise falls back to tier limit).
    2. Calculates `points_over` (how far past the limit the discount goes).
    3. Calculates `blended_score` (the sum of `points_over` across all lines to catch "death by a thousand cuts" margin erosion).
    4. Evaluates `severity` (the maximum of the worst single line or the blended score) and maps it to an approval level (`none`, `manager`, `manager_then_finance`).

* **`quote_loader.py`**
  - Acts as a bridge between the Database (SQLAlchemy) and the Domain logic (Risk Engine).
  - Exposes `build_line_inputs()` which runs the SQL JOINs to fetch a quote's lines, products, categories, and customer tiers, translating database rows into the clean `LineInput` dataclasses required by the risk engine.

### API Controllers (`backend/app/routers/`)

* **`quotes.py`**
  - The REST API surface for the frontend to interact with. Uses FastAPI dependency injection (`Depends(get_db)`) to safely open and close database sessions for every request.
  - **Endpoints:**
    - `POST /{quote_id}/evaluate`: Read-only endpoint that runs the quote through the risk engine and returns the evaluation.
    - `POST /{quote_id}/submit`: Evaluates the quote, updates the Quote's status based on the required approval routing, and logs an `AuditLog` entry.
    - `POST /{quote_id}/approval-action`: Processes approvals, rejections, and revisions from managers and finance. Enforces sequential routing (e.g., moving a quote from manager to finance) and writes both `ApprovalAction` and `AuditLog` rows.
    - `GET /pending-approval`: Fetches queues of quotes waiting for action, filterable by step (e.g., `?step=manager`).
    - `GET /{quote_id}/approval-history`: Returns the timeline of all `ApprovalAction` and `AuditLog` rows for frontend display.

### Testing Suite (`backend/tests/`)

* **`test_risk_engine.py`**
  - Unit tests focused strictly on the math in `risk_engine.py`. Verifies edge cases (e.g., category overriding tier, blended threshold violations, clean quotes passing without approval).

* **`test_approval_workflow.py`**
  - Integration tests using FastAPI's `TestClient` and an in-memory SQLite database (`StaticPool`).
  - Simulates end-to-end API requests. Verifies that auto-approvals happen correctly, quotes route from manager to finance, rejections halt the pipeline, and invalid state transitions return `400 Bad Request` errors.

---

## 3. Frontend Implementation Details

* **`frontend/package.json`**
  - Defines the core stack: Next.js 16.3.4, React 19, and Tailwind CSS v4.

* **`frontend/app/` (Next.js App Router)**
  - `layout.tsx`: The root HTML structure, wrapping the application. Sets up global fonts and CSS.
  - `page.tsx`: The entry point UI component. Currently contains basic boilerplate styling.
  - `globals.css`: Tailwinds integration via `@import "tailwindcss"`. 
  - (Upcoming): Will house components for the Deals Dashboard, Quote Builder, and Manager Inbox.

---

## 4. How Data Flows (Example: Submitting a Quote)

1. **Client Request**: Frontend sends `POST /quotes/1/submit`.
2. **Controller (quotes.py)**: FastAPI receives the request and injects a DB session.
3. **Database Fetch**: Controller fetches `Quote` with ID 1. Validates it is in `"draft"` status.
4. **Data Transformation (quote_loader.py)**: The DB session is passed to `build_line_inputs()`, which queries the `quote_lines`, joins `products`, `categories`, and the `customer_tier`, and maps them into a list of `LineInput` objects.
5. **Business Logic (risk_engine.py)**: The list is passed to `evaluate_quote(lines)`. The engine does pure math to calculate points over limits and returns a `QuoteRiskResult` indicating `"manager"` approval is required.
6. **State Mutation**: Controller updates `Quote.status` to `"pending_approval"` and `current_approval_step` to `"manager"`.
7. **Audit**: Controller instantiates an `AuditLog` mapping the action.
8. **Commit & Return**: `db.commit()` saves all changes transactionally. API returns the updated quote and risk profile to the client.
