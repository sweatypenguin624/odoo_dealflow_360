# 7. Request / Response Flows

This section traces the end-to-end execution path of the three most critical workflows in DealFlow360.

## Workflow 1: Submitting a Quote for Approval

```text
Client
  ↓ POST /quotes/{id}/submit
Router (quotes.py)
  ↓ 
Service (quote_loader.py)
  ↓ Queries DB for Quote and QuoteLines, builds `LineInput` dataclasses
Service (risk_engine.py)
  ↓ Evaluates line discounts against CustomerTier and Category maximums
Router (quotes.py)
  ↓ Updates Quote.status (to 'approved' or 'pending_approval')
  ↓ Creates AuditLog entry
  ↓ Commits to Database
Client (Receives Quote and RiskResult JSON)
```

**What Happens?**
When a quote is submitted, the API does not just blindly accept it. It converts the database models into plain data structures (`LineInput`) and passes them to `evaluate_quote()`. The Risk Engine checks if the requested discounts exceed the allowable limits for the customer's tier or the product's category. It returns a `QuoteRiskResult` dictating whether it requires "manager" or "finance" approval, or if it can be auto-approved.

---

## Workflow 2: Fulfilling an Approved Quote

```text
Client
  ↓ POST /quotes/{id}/fulfillment/suggest
Router (fulfillment.py)
  ↓ Verifies Quote status is 'approved'
  ↓ Queries `Stock` for all required products
Service (fulfillment_engine.py)
  ↓ plan_fulfillment() executes the routing logic
  ↓ Iterates over needed lines, deducts from available stock across warehouses
  ↓ Generates Warehouse Allocations and Backorders
Router (fulfillment.py)
  ↓ Saves `FulfillmentPlan` (status = 'suggested')
  ↓ Saves `FulfillmentSplit`s to DB
Client (Receives FulfillmentPlan JSON with Backorder Summary)
```

**What Happens?**
The user asks the system to figure out how to ship the quote. The backend gathers all available stock across all warehouses and passes it to the `fulfillment_engine`. The engine attempts to fulfill the order from a single warehouse to minimize shipping costs, but will split the order across multiple warehouses if necessary, or generate backorders if stock is entirely depleted.

**Confirmation Phase:**
The user then calls `POST /quotes/{id}/fulfillment/confirm`. At this exact moment, the router queries the `Stock` table using `.with_for_update()` (row-level locking). It checks if the stock is still there, deducts the quantities, updates the plan to `confirmed`, and commits the transaction, ensuring no race conditions oversell the stock.

---

## Workflow 3: Upsell Recommendations

```text
Client
  ↓ GET /quotes/{id}/upsell-suggestions?limit=5
Router (upsell.py)
  ↓ Queries `ProductPairing` to find Candidates based on current QuoteLines
Service (upsell_engine.py)
  ↓ calculate_margin_summary() 
  ↓ rank_upsell_suggestions()
    ↓ (Internal) Prepares features (margins, historical scores)
    ↓ (Internal) Inferences the XGBoost `recommendation_model.json`
  ↓ Sorts candidates by predicted probability and margin score
Client (Receives list of RankedSuggestions JSON)
```

**What Happens?**
The client requests upsells for a draft quote. The router queries the `ProductPairing` table to get a rough pool of candidates. These candidates are passed to the `upsell_engine`. The engine prepares a feature vector for each candidate (incorporating unit margins, co-purchase scores) and runs it through the pre-loaded XGBoost model. The model predicts the probability of the user accepting the upsell. The engine ranks them by a blend of probability and profitability (margin), returning the top N suggestions.
