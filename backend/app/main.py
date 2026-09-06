import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import settings
from app.core.errors import AppError
from app.core.logging import RequestLoggingMiddleware, configure_logging, request_id_ctx

configure_logging()
logger = logging.getLogger("dealflow")

TAGS_METADATA = [
    {"name": "auth", "description": "Sign-in, session refresh, password reset."},
    {"name": "users", "description": "User administration (admin only)."},
    {"name": "customers", "description": "Customer accounts, tiers and history."},
    {"name": "catalog", "description": "Products, variants and categories."},
    {"name": "pricing", "description": "Price lists, discount rules and approval rules."},
    {"name": "quotes", "description": "Quotation lifecycle: draft → approval → send → negotiate → confirm."},
    {"name": "approvals", "description": "Approval queue and decisions."},
    {"name": "upsell", "description": "Margin summary and cross-sell recommendations."},
    {"name": "inventory", "description": "Warehouses, stock levels and movements."},
    {"name": "fulfillment", "description": "Warehouse allocation, shipments and backorders."},
    {"name": "subscriptions", "description": "Recurring subscriptions, proration and billing runs."},
    {"name": "invoices", "description": "Invoices, payments and refunds."},
    {"name": "deal-health", "description": "Alerts, nudges and escalations."},
    {"name": "notifications", "description": "In-app notification inbox."},
    {"name": "reports", "description": "Analytics and exports."},
    {"name": "search", "description": "Global search."},
    {"name": "portal", "description": "Customer-facing portal (token or customer login)."},
    {"name": "health", "description": "Liveness / readiness."},
]

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="DealFlow360 — B2B sales operations platform API.",
    openapi_tags=TAGS_METADATA,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Content-Disposition"],
)
app.add_middleware(RequestLoggingMiddleware)


def _error_body(detail: str, code: str, errors=None, status_code: int = 400) -> JSONResponse:
    body = {"detail": detail, "code": code, "request_id": request_id_ctx.get()}
    if errors:
        body["errors"] = errors
    return JSONResponse(status_code=status_code, content=body)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    return _error_body(exc.message, exc.code, exc.details, exc.status_code)


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    code = {401: "unauthenticated", 403: "forbidden", 404: "not_found", 409: "conflict"}.get(exc.status_code, "error")
    response = _error_body(detail, code, None, exc.status_code)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(p) for p in e.get("loc", []) if p != "body"), "message": e.get("msg")}
        for e in exc.errors()
    ]
    first = errors[0] if errors else None
    detail = f"{first['field']}: {first['message']}" if first and first["field"] else "Invalid request."
    return _error_body(detail, "validation_error", errors, 422)


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception):
    logger.exception("unhandled error")
    return _error_body("Something went wrong on our side. Please try again.", "internal_error", None, 500)


app.include_router(api_router)
