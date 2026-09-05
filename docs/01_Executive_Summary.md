# 1. Executive Summary

## Project Purpose
`odoo_dealflow_360` is a comprehensive backend application (with an initialized Next.js frontend) designed to manage the lifecycle of deals, quotes, fulfillment, subscriptions, and upsell/cross-sell opportunities. 

At its core, DealFlow360 solves the problem of disconnected sales operations by providing a unified API that handles:
1. **Quoting and Approvals**: Creating quotes with line items, evaluating them for risk, and triggering approval workflows based on predefined business logic.
2. **Order Fulfillment**: Splitting quotes into actionable warehouse fulfillment plans and tracking stock.
3. **Subscription Billing**: Managing recurring revenue by converting quotes into active subscription plans with billing intervals.
4. **Machine Learning-Driven Upselling**: Leveraging an Apriori algorithm and a custom ML pipeline to analyze historical invoice data and recommend product pairings to maximize deal value.

## Who/What Interacts with It
- **Sales Representatives**: Generate quotes and view upsell recommendations.
- **Managers / Automated Risk Engines**: Review high-risk or high-discount quotes for approval.
- **Warehouse Operations**: Receive fulfillment plans to pick and ship products.
- **Billing Systems**: Track billing events (e.g., charge, refund, trial) for active subscriptions.

The system acts as the central hub ("DealFlow") where a deal enters as a draft quote and exits as a fulfilled order or an active subscription, augmented by intelligent cross-selling rules.
