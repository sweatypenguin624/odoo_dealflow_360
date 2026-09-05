# 12. Module Documentation

This section provides a directory-level breakdown of module dependencies and responsibilities.

## `app/models/`
- **Responsibility**: Database schemas and SQLAlchemy ORM mapping.
- **Dependencies**: Depends heavily on `sqlalchemy`.
- **Dependents**: Used by almost everything in `app/routers/` and `app/services/quote_loader.py`.
- **Key Note**: Business logic is strictly prohibited here. Models are dumb data containers.

## `app/routers/`
- **Responsibility**: The HTTP/API boundary. Defines routes, parses request bodies, and serializes responses.
- **Dependencies**: Depends on `fastapi`, `pydantic`, `app.models`, and `app.services`.
- **Dependents**: Used by `main.py` (which includes the routers).
- **Key Note**: Routers handle HTTP exceptions (`404`, `400`) and database session commits/rollbacks. They act as the orchestration layer between the database and the engines.

## `app/services/`
- **Responsibility**: Pure business logic (Risk, Fulfillment, Billing, Upsell).
- **Dependencies**: `dataclasses`, `dateutil`.
- **Dependents**: `app.routers`.
- **Key Note**: The `_engine.py` files purposely have no dependency on FastAPI or SQLAlchemy. However, `quote_loader.py` exists specifically to bridge `app.models` and the engines.

## `upsell_cross_sell/`
- **Responsibility**: Offline machine learning and data generation.
- **Dependencies**: `pandas`, `numpy`, `xgboost`, `scikit-learn`.
- **Dependents**: Output JSON is read by `app/services/upsell_engine.py` in the backend.
- **Key Note**: Completely decoupled from the FastAPI application. It is run via command line (e.g., `python build_training_data.py`).
