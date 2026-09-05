# 26. Final Mental Model

To successfully develop within the `odoo_dealflow_360` repository, you should hold the following mental model:

**1. DealFlow is a Pipeline**
Everything begins as a `Quote`. A Quote is just a bucket of requested items. 
The system's job is to pass this bucket through a series of checkpoints:
- **Checkpoint 1 (Upsell)**: "Can we put more things in the bucket?" (Powered by ML).
- **Checkpoint 2 (Risk)**: "Are the discounts in this bucket safe?" (Powered by rules).
- **Checkpoint 3 (Split)**: "The bucket is approved. Where do the contents go?" Physical items go to Warehouse fulfillment. Recurring items go to Subscriptions.

**2. The Database is Dumb; The Engines are Smart**
Do not put logic into SQLAlchemy models (e.g., `def is_approved(self):`). 
Do not put logic into FastAPI routers.
If you need to calculate something, you create a plain Python dataclass, pass it into a function in `app/services/`, and return the result. The router handles the database translation.

**3. The ML Pipeline is an Offline Sidekick**
The backend API does not train models. It only reads the final JSON artifact (`recommendation_model.json`). If the ML team breaks the training script, the API stays up. If the API goes down, the ML team can keep training. They are decoupled.

**4. Follow the Money and the Stock**
Changes to Subscriptions must always generate an immutable `BillingEvent`. 
Changes to Warehouses must always lock the `Stock` table before decrementing. 
Never update a quantity without leaving a paper trail.

By adhering to this model, you can safely scale DealFlow360 to handle thousands of quotes, warehouses, and complex subscription tiers.
