from fastapi import APIRouter

from app.api.routes import (
    approvals, auth, catalog, customers, dashboard, deal_health, fulfillment, health, inventory, invoices, notifications, portal, pricing,
    quotes, reports, search, settings, subscriptions, upsell, users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(settings.router)
api_router.include_router(customers.router)
api_router.include_router(catalog.router)
api_router.include_router(pricing.router)
api_router.include_router(quotes.router)
api_router.include_router(approvals.router)
api_router.include_router(upsell.router)
api_router.include_router(portal.router)
api_router.include_router(notifications.router)
api_router.include_router(inventory.router)
api_router.include_router(fulfillment.router)
api_router.include_router(subscriptions.router)
api_router.include_router(invoices.router)
api_router.include_router(deal_health.router)
api_router.include_router(dashboard.router)
api_router.include_router(reports.router)
api_router.include_router(search.router)
