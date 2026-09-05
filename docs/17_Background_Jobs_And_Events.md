# 17. Background Jobs and Events

## Current State
The backend is currently a synchronous REST API. There are no asynchronous background workers (like Celery or Redis Queue) integrated into the FastAPI runtime.

## Machine Learning Pipeline
The only "background" tasks are the ML pipeline scripts located in `backend/upsell_cross_sell/ml/`.
These are executed manually via the command line, rather than triggered by API events.

1. `python build_training_data.py`: Rebuilds the CSV datasets based on historical invoices.
2. `python train_model.py`: Trains the XGBoost model and saves `recommendation_model.json`.

In a production environment, these scripts would likely be scheduled via a Cron job or an orchestration tool like Airflow to retrain the model weekly based on new invoice data.
