from fastapi import FastAPI

from app.routers import quotes

app = FastAPI(title="DealFlow360 API")
app.include_router(quotes.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}