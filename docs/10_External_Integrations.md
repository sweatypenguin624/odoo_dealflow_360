# 10. External Integrations

## Current State
The `odoo_dealflow_360` application is currently **fully self-contained**. It does not interact with any external SaaS APIs, payment gateways, or third-party webhooks.

## Design Implications

### 1. Payments & Billing (Stripe / Recurly)
The `BillingEngine` currently generates internal `BillingEvent` records (e.g., `invoice`, `proration_charge`) stored in SQLite. It calculates exact prorated amounts natively. 
- **Future Integration**: In a real-world scenario, this engine would likely sit in front of Stripe. Instead of just saving a `BillingEvent`, the `SubscribeRequest` would trigger a Stripe API call to create a Subscription object on their servers. 

### 2. ERP / Warehouse Management System (WMS)
The `FulfillmentEngine` performs complex inventory allocations based on the local `Stock` table.
- **Future Integration**: Real warehouses operate via dedicated WMS software. The confirmation of a `FulfillmentPlan` would likely fire a webhook or an API request to a 3PL (Third Party Logistics) provider to physically pick and pack the boxes. The local `Stock` table would need to be periodically synced with the actual warehouse counts via API.

### 3. CRM Integration (Salesforce / HubSpot)
The `Quote` and `Customer` tables act as a mini-CRM.
- **Future Integration**: DealFlow360 would likely act as a CPQ (Configure, Price, Quote) add-on to a larger CRM. Quotes would originate in Salesforce, sync via API to DealFlow360 for complex fulfillment/billing/upsell calculations, and sync back to the CRM upon approval.

### Conclusion
By keeping the application self-contained, the business logic (Risk, Fulfillment, Billing, ML) can be developed and tested rapidly without dealing with flaky third-party sandboxes or network latency. The boundaries where external integrations should occur are clearly defined by the Domain Engine boundaries.
