from fastapi import FastAPI

from app.routers import quotes, fulfillment

app = FastAPI(title="DealFlow360 API")
app.include_router(quotes.router)
app.include_router(fulfillment.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}