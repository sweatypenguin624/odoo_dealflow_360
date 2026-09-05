from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import quotes, fulfillment, upsell, billing, portal, dashboard, catalog, invoices

app = FastAPI(title="DealFlow360 API")

# Frontend gap-fill (Phase 8): the workspace UI calls this API directly
# from the browser, which the default same-origin policy would block
# entirely without this.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(quotes.router)
app.include_router(fulfillment.router)
app.include_router(upsell.router)
app.include_router(billing.router)
app.include_router(portal.router)
app.include_router(dashboard.router)
app.include_router(catalog.router)
app.include_router(invoices.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}