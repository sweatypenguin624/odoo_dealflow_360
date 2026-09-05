from fastapi import FastAPI

app = FastAPI(title="DealFlow360 API")

@app.get("/health")
def health_check():
    return {"status": "ok"}