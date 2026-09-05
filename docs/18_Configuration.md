# 18. Configuration and Environment Variables

The backend relies on `pydantic-settings` to manage configuration, ensuring the app crashes at startup if critical variables are missing or incorrectly typed.

## `backend/app/config.py`

### `DATABASE_URL`
- **Purpose**: Defines the SQLAlchemy connection string.
- **Default**: `sqlite:///./dealflow.db`
- **Usage**: Used in `database.py` to instantiate the `create_engine()`.
- **Production Impact**: In production, this would be set to a PostgreSQL connection string (e.g., `postgresql://user:pass@host/db`).

## Machine Learning Hardware Config
In `train_model.py`, the script accepts command-line arguments rather than environment variables:
- `--device`: Can be `cuda` or `cpu`. Defaults to `cuda` but contains fallback logic if CUDA is unavailable on the host machine.
