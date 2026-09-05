# 21. End-To-End Feature Walkthrough

Let's walk through the lifespan of a deal in DealFlow360.

## 1. The Deal Begins (Drafting a Quote)
A Sales Rep interacts with the frontend to build a quote for a "Gold" tier customer. They add three lines:
- 10x Laptops (Physical) at 12% discount.
- 1x Setup Fee (Physical) at 18% discount.
- 50x SaaS Licenses (Recurring) at 0% discount.

## 2. ML Upsell Recommendation
While drafting, the frontend requests `GET /quotes/{id}/upsell-suggestions`.
The API fetches `ProductPairings` from the DB, runs the `UpsellEngine`'s XGBoost model in real-time, and recommends a "Premium Support" package because it has high margin and a high probability of conversion. The rep clicks "Add" on the frontend, hitting `POST /quotes/.../add-suggestion`, appending a 4th line to the quote.

## 3. Submission & Risk Evaluation
The Rep clicks "Submit" (`POST /quotes/{id}/submit`).
The `RiskEngine` runs. The Laptops (12%) are fine because the Gold tier limit is 15%. However, the Setup Fee (18%) exceeds the 15% limit by 3 points. 
Because the max severity is 3 points (which is less than the MANAGER_THRESHOLD of 5), the quote is actually **auto-approved**. Its status immediately transitions to `approved`.

## 4. Splitting the Paths
Because the quote is now `approved`, two parallel workflows can begin.

### 4a. Fulfillment (The Laptops & Setup Fee)
Ops clicks "Plan Shipping" (`POST /quotes/{id}/fulfillment/suggest`).
The `FulfillmentEngine` looks for 10 Laptops and 1 Setup Fee in the DB's `Stock` tables. It finds a cheap warehouse with 8 laptops, and an expensive warehouse with 10 laptops. It chooses the expensive one to avoid splitting the shipment into two boxes. Ops reviews this and clicks `Confirm`. The 10 laptops are deducted from the database.

### 4b. Billing (The SaaS Licenses & Premium Support)
Finance clicks "Start Subscriptions". 
The `BillingEngine` converts the two recurring quote lines into active `Subscription` records. It calculates the `next_cycle_date` and generates the initial `invoice` BillingEvents for the first month.

## 5. The Deal is Closed
The deal has successfully moved from a draft into fulfilled physical boxes and recurring SaaS revenue, fully documented in the `AuditLog` table.
