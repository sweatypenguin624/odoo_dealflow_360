# 5. Application Startup / Initialization

This section explains exactly what happens when the `odoo_dealflow_360` backend boots up.

## Entry Point: `backend/app/main.py`
The FastAPI backend is typically started via Uvicorn:
`uvicorn app.main:app --reload`

When this command runs, the following sequence occurs:

1. **Configuration Loading (`app/config.py`)**:
   - `pydantic-settings` instantiates the `Settings` class.
   - It looks for a `.env` file in the root directory.
   - It reads `database_url` (defaulting to `sqlite:///./dealflow.db` if not found).
   - If a required environment variable were missing, the application would crash here before the server even starts, ensuring fail-safe configuration.

2. **Database Initialization (`app/database.py`)**:
   - `create_engine()` is called using the `database_url`.
   - `SessionLocal` is created, which is a factory for database sessions.
   - Importantly, **tables are not automatically created here**. The project relies on Alembic for migrations. If you boot the app against an empty SQLite file, you must run `alembic upgrade head` first.

3. **Application Instantiation (`app/main.py`)**:
   - `app = FastAPI(title="DealFlow360 API")` creates the ASGI application object.

4. **Router Registration (`app/main.py`)**:
   - The app registers all endpoints via `app.include_router()`.
   - It imports `quotes`, `fulfillment`, `upsell`, and `billing` routers.
   - Python processes the `import` statements for these routers. **This is critical** because importing the routers causes the underlying Engine modules (like `upsell_engine.py`) to be imported.

5. **Engine Initialization & ML Model Loading**:
   - While the standard routers are lightweight, importing `app.services.upsell_engine` triggers the loading of the Machine Learning models.
   - If the `upsell_engine.py` (which we will analyze in later chapters) loads the `recommendation_model.json` at module level, this happens during startup. If the model file is missing, startup may fail or default to a fallback.

6. **Ready for Requests**:
   - Uvicorn binds to the designated port (usually `8000`).
   - The `/health` endpoint is immediately available to return `{"status": "ok"}`.

## What happens when a request arrives?
When a client hits an endpoint (e.g., `POST /quotes`):
1. **Pydantic Validation**: FastAPI parses the JSON body and validates it against the Pydantic schema defined in the router. If validation fails, it immediately returns a `422 Unprocessable Entity`.
2. **Dependency Injection**: FastAPI resolves dependencies. The most common dependency is `get_db()`, which yields a `SessionLocal` from `database.py`.
3. **Execution**: The router hands the payload and the database session to the appropriate Service Engine (e.g., `QuoteLoader.create_quote`).
4. **Cleanup**: After the response is sent, the `get_db()` dependency generator executes its `finally` block, closing the database session and returning the connection to the pool.
