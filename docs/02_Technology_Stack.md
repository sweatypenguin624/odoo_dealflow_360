# 2. Technology Stack

`odoo_dealflow_360` utilizes a modern, modular technology stack separated into three main layers: a frontend application, a backend API, and a machine learning pipeline.

## Backend (API & Core Logic)
- **Language**: Python 3.x
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (version 0.141.1) for high-performance, asynchronous REST API generation.
- **Server**: [Uvicorn](https://www.uvicorn.org/) (version 0.52.4) serving as the ASGI server.
- **Data Validation**: [Pydantic](https://docs.pydantic.dev/) for robust request/response modeling and `pydantic-settings` for environment configuration.
- **Database ORM**: [SQLAlchemy](https://www.sqlalchemy.org/) (version 2.0.52) handles database interactions via object-relational mapping.
- **Database Migrations**: [Alembic](https://alembic.sqlalchemy.org/) manages schema changes (found in `backend/alembic/`).
- **Database Engine**: Currently configured to use **SQLite** (`sqlite:///./dealflow.db`), though `psycopg2-binary` is installed, indicating readiness for PostgreSQL in production.
- **Testing**: [Pytest](https://docs.pytest.org/) handles the test suite.

## Machine Learning Pipeline
The ML pipeline powers the Upsell and Cross-sell recommendations.
- **Data Processing**: [Pandas](https://pandas.pydata.org/) and [NumPy](https://numpy.org/) are heavily utilized in `build_training_data.py` to calculate historical spend, frequency, and affinities.
- **Model**: [XGBoost](https://xgboost.readthedocs.io/) (`xgb.XGBClassifier`) is the core model used to predict the likelihood of a customer accepting a cross-sell or upsell recommendation.
- **Evaluation**: `scikit-learn` provides evaluation metrics like ROC AUC, Precision, and Recall.

## Frontend
- **Framework**: [Next.js 16](https://nextjs.org/) (React 19) bootstrapped using `create-next-app`.
- **Styling**: [Tailwind CSS v4](https://tailwindcss.com/) for utility-first styling.
- **Language**: TypeScript (`.tsx`, `.ts`).
- **State**: The frontend currently acts as an initialized placeholder scaffold. The heavy lifting of the DealFlow360 business logic resides in the backend and ML services.

## Why this Stack?
- **FastAPI + SQLAlchemy**: Provides strict typing and immediate validation. Given the complex nature of quotes, pricing, and fulfillment models, typing prevents pervasive business logic errors.
- **XGBoost**: Tree-based models handle tabular, non-linear categorical data (like product categories, brands, and customer tiers) exceptionally well, making it ideal for the `upsell_cross_sell` recommendations compared to deep learning approaches.
- **Next.js**: Provides a robust foundation for building complex B2B dashboards with Server-Side Rendering (SSR) capabilities.
