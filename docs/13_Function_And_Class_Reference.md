# 13. Function and Class Reference

A detailed reference for the most critical functions spanning the application.

## 1. `evaluate_quote(lines: List[LineInput]) -> QuoteRiskResult`
- **Module**: `app/services/risk_engine.py`
- **Purpose**: Evaluates a quote's discount levels to determine approval requirements.
- **Inputs**: A list of `LineInput` dataclasses.
- **Input Sources**: `quote_loader.build_line_inputs()` builds these from DB models.
- **Output**: `QuoteRiskResult` containing a `blended_score` and `required_approval_level`.
- **Side Effects**: None. Pure function.
- **Callers**: `quotes.evaluate_quote_risk` and `quotes.submit_quote`.
- **Edge Cases**: If a product has no category limit, the tier limit applies.

## 2. `plan_fulfillment(lines: List[LineToFulfill], stock_by_product: Dict[int, List[WarehouseStockInput]]) -> FulfillmentResult`
- **Module**: `app/services/fulfillment_engine.py`
- **Purpose**: Creates an optimal shipping manifest.
- **Inputs**: Needed lines, and a dictionary mapping `product_id` to a list of available warehouse stocks.
- **Output**: A `FulfillmentResult` containing `SplitAllocation`s (who ships what).
- **Side Effects**: None. Pure function. (Stock decrementing happens in-memory only).
- **Callers**: `fulfillment.suggest_fulfillment`.

## 3. `calculate_proration(subscription: SubscriptionState, new_quantity: int, change_date: date) -> ProrationResult`
- **Module**: `app/services/billing_engine.py`
- **Purpose**: Calculates the charge/credit when a user changes their seat count mid-cycle.
- **Inputs**: Current `SubscriptionState`, the `new_quantity`, and the `change_date`.
- **Output**: `ProrationResult` indicating the exact float amount to charge/credit.
- **Side Effects**: None.
- **Callers**: `billing.change_subscription_quantity`.
- **Edge Cases**: If `change_date` is after the cycle ends, proration is $0.

## 4. `build_training_data()`
- **Module**: `upsell_cross_sell/ml/build_training_data.py`
- **Purpose**: The workhorse of the ML pipeline. Generates tabular data from raw CSVs.
- **Inputs**: Reads `products.csv`, `customers.csv`, `invoices.csv`, etc., from the disk.
- **Output**: Writes `ml_training.csv` and `ml_validation.csv` to disk (80/20 chronological split).
- **Side Effects**: Heavy disk I/O.
- **Execution Flow**: 
  1. Loads all CSVs into pandas.
  2. Sorts invoices chronologically.
  3. Iterates over every invoice line.
  4. Keeps a running state dictionary of customer spend and affinities.
  5. Uses Apriori rules to generate "fake" upsell/cross-sell candidates.
  6. Compares candidates to what was *actually* purchased on that invoice to generate binary `target` labels (1=accepted, 0=rejected).

## 5. `train_model()`
- **Module**: `upsell_cross_sell/ml/train_model.py`
- **Purpose**: Trains the XGBoost classifier.
- **Inputs**: `ml_training.csv` and `ml_validation.csv`.
- **Output**: `recommendation_model.json` and `model_metadata.json`.
- **Side Effects**: Writes binary model to disk.
- **Error Behavior**: Will fail if CUDA is requested but unavailable, falling back to CPU. Will crash if `ml_training.csv` is missing.
