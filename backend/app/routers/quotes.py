from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import Customer, Product, Quote, QuoteLine, QuoteStatus, AuditLog, ApprovalAction
from app.services.risk_engine import LineInput, QuoteRiskResult, evaluate_quote
from app.services.quote_loader import build_line_inputs

router = APIRouter(prefix="/quotes", tags=["quotes"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/pending-approval")
def get_pending_approval(step: Optional[str] = Query(None), db: Session = Depends(get_db)):
    query = db.query(Quote).filter(Quote.status == QuoteStatus.pending_approval)
    if step:
        query = query.filter(Quote.current_approval_step == step)
    quotes = query.all()
    # Phase 10 fix: this used to return raw ORM rows, which never carried
    # customer_name - the Approvals list screen (Phase 8) has been reading
    # that field since it was built, so it was always coming back
    # undefined. Reuses the same helper list_quotes() uses below.
    return [_quote_list_item(quote) for quote in quotes]


@router.post("/{quote_id}/evaluate", response_model=QuoteRiskResult)
def evaluate_quote_risk(quote_id: int, db: Session = Depends(get_db)) -> QuoteRiskResult:
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")

    line_inputs = build_line_inputs(quote_id, db, quote)
    return evaluate_quote(line_inputs)


@router.post("/{quote_id}/submit")
def submit_quote(quote_id: int, db: Session = Depends(get_db)):
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")
        
    if quote.status != QuoteStatus.draft:
        raise HTTPException(status_code=400, detail="Only draft quotes can be submitted")

    line_inputs = build_line_inputs(quote_id, db, quote)
    risk_result = evaluate_quote(line_inputs)

    quote.required_approval_level = risk_result.required_approval_level
    quote.risk_reasons = risk_result.reasons

    if risk_result.required_approval_level == "none":
        quote.status = QuoteStatus.approved
        quote.current_approval_step = None
        
        audit = AuditLog(
            quote_id=quote.id,
            user="system",
            action="auto_approved",
            reason="No approval required — all lines within limits."
        )
        db.add(audit)
    elif risk_result.required_approval_level == "manager":
        quote.status = QuoteStatus.pending_approval
        quote.current_approval_step = "manager"
    elif risk_result.required_approval_level == "manager_then_finance":
        quote.status = QuoteStatus.pending_approval
        quote.current_approval_step = "manager"
        
    submission_reason = " | ".join(risk_result.reasons) if risk_result.reasons else "No violations found"
    db.add(AuditLog(
        quote_id=quote.id,
        user="system", 
        action="submitted",
        reason=submission_reason
    ))
    
    db.commit()
    db.refresh(quote)
    return {"quote": quote, "risk_result": risk_result}


class ApprovalActionRequest(BaseModel):
    actor: str
    action: str 
    note: Optional[str] = None


@router.post("/{quote_id}/approval-action")
def approval_action(quote_id: int, req: ApprovalActionRequest, db: Session = Depends(get_db)):
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")
        
    if quote.status != QuoteStatus.pending_approval or quote.current_approval_step is None:
        raise HTTPException(status_code=400, detail="Quote is not pending approval")
        
    if req.action not in ("approved", "rejected", "returned_for_revision"):
        raise HTTPException(status_code=400, detail="Invalid action")
        
    step_acted_on = quote.current_approval_step
    audit_reason = req.note or f"Action {req.action} by {step_acted_on}"
    
    approval = ApprovalAction(
        quote_id=quote.id,
        step=step_acted_on,
        action=req.action,
        actor=req.actor,
        reason=req.note
    )
    db.add(approval)
    
    if req.action == "rejected":
        quote.status = QuoteStatus.rejected
        quote.current_approval_step = None
    elif req.action == "returned_for_revision":
        quote.status = QuoteStatus.draft
        quote.current_approval_step = None
        quote.required_approval_level = None
    elif req.action == "approved":
        if step_acted_on == "manager" and quote.required_approval_level == "manager_then_finance":
            quote.current_approval_step = "finance"
            audit_reason = "Manager approved — routed to Finance for final approval."
        else:
            quote.status = QuoteStatus.approved
            quote.current_approval_step = None
            audit_reason = "Fully approved."
            
    audit = AuditLog(
        quote_id=quote.id,
        user=req.actor,
        action=req.action,
        reason=audit_reason
    )
    db.add(audit)
    
    db.commit()
    db.refresh(quote)
    
    history = db.query(ApprovalAction).filter(ApprovalAction.quote_id == quote.id).order_by(ApprovalAction.timestamp).all()
    
    return {"quote": quote, "history": history}


@router.get("/{quote_id}/approval-history")
def get_approval_history(quote_id: int, db: Session = Depends(get_db)):
    approval_actions = db.query(ApprovalAction).filter(ApprovalAction.quote_id == quote_id).order_by(ApprovalAction.timestamp).all()
    audit_logs = db.query(AuditLog).filter(AuditLog.quote_id == quote_id).order_by(AuditLog.timestamp).all()
    return {
        "approval_actions": approval_actions,
        "audit_logs": audit_logs
    }


# ---- Frontend gap-fill (Phase 8): no earlier phase exposed a way to list
# quotes, fetch one quote's full detail with product names, or edit an
# existing line's quantity/discount - the workspace UI can't function
# without these, so they're added here as plain, additive read/write
# endpoints rather than worked around client-side. ----


class QuoteListItemResponse(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    status: str
    required_approval_level: Optional[str]
    current_approval_step: Optional[str]
    created_at: Optional[str]

    class Config:
        from_attributes = True


class QuoteLineDetailResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    discount_pct: float
    line_value: float
    is_recurring: bool


class QuoteDetailResponse(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    status: str
    required_approval_level: Optional[str]
    current_approval_step: Optional[str]
    risk_reasons: Optional[List[str]]
    created_at: Optional[str]
    lines: List[QuoteLineDetailResponse]


def _quote_list_item(quote: Quote) -> QuoteListItemResponse:
    return QuoteListItemResponse(
        id=quote.id,
        customer_id=quote.customer_id,
        customer_name=quote.customer.name,
        status=quote.status.value,
        required_approval_level=quote.required_approval_level,
        current_approval_step=quote.current_approval_step,
        created_at=quote.created_at.isoformat() if quote.created_at else None,
    )


@router.get("", response_model=List[QuoteListItemResponse])
def list_quotes(db: Session = Depends(get_db)):
    quotes = db.query(Quote).order_by(Quote.id.desc()).all()
    return [_quote_list_item(quote) for quote in quotes]


# ---- Phase 10 gap-fill: no earlier phase exposed a way to create a new
# quotation from scratch - only editing an existing quote's lines was
# built. The Dashboard's "+ New Quotation" button needs a real starting
# point, so this is added here as a plain, additive create endpoint,
# following the same pattern as Phase 8's other gap-fills. ----


class NewQuoteLineRequest(BaseModel):
    product_id: int
    quantity: int
    discount_pct: float = 0


class QuoteCreateRequest(BaseModel):
    customer_id: int
    rep_name: Optional[str] = None
    lines: List[NewQuoteLineRequest] = []


@router.post("", response_model=QuoteDetailResponse)
def create_quote(payload: QuoteCreateRequest, db: Session = Depends(get_db)):
    customer = db.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    quote = Quote(customer_id=payload.customer_id, status=QuoteStatus.draft, rep_name=payload.rep_name)
    db.add(quote)
    db.flush()

    for line in payload.lines:
        product = db.get(Product, line.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail=f"Product {line.product_id} not found")
        db.add(
            QuoteLine(
                quote_id=quote.id,
                product_id=line.product_id,
                quantity=line.quantity,
                discount_pct=line.discount_pct,
                line_value=product.price * line.quantity,
            )
        )

    db.commit()
    db.refresh(quote)
    return get_quote_detail(quote.id, db)


@router.get("/{quote_id}", response_model=QuoteDetailResponse)
def get_quote_detail(quote_id: int, db: Session = Depends(get_db)):
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")

    lines = (
        db.query(QuoteLine, Product)
        .join(Product, QuoteLine.product_id == Product.id)
        .filter(QuoteLine.quote_id == quote_id)
        .all()
    )

    return QuoteDetailResponse(
        id=quote.id,
        customer_id=quote.customer_id,
        customer_name=quote.customer.name,
        status=quote.status.value,
        required_approval_level=quote.required_approval_level,
        current_approval_step=quote.current_approval_step,
        risk_reasons=quote.risk_reasons,
        created_at=quote.created_at.isoformat() if quote.created_at else None,
        lines=[
            QuoteLineDetailResponse(
                id=quote_line.id,
                product_id=quote_line.product_id,
                product_name=product.name,
                quantity=quote_line.quantity,
                discount_pct=quote_line.discount_pct,
                line_value=quote_line.line_value,
                is_recurring=quote_line.is_recurring,
            )
            for quote_line, product in lines
        ],
    )


class LineUpdateRequest(BaseModel):
    quantity: Optional[int] = None
    discount_pct: Optional[float] = None


@router.patch("/{quote_id}/lines/{line_id}", response_model=QuoteLineDetailResponse)
def update_quote_line(
    quote_id: int, line_id: int, payload: LineUpdateRequest, db: Session = Depends(get_db)
):
    line = (
        db.query(QuoteLine).filter(QuoteLine.id == line_id, QuoteLine.quote_id == quote_id).first()
    )
    if line is None:
        raise HTTPException(status_code=404, detail="Quote line not found on this quote")

    product = db.get(Product, line.product_id)

    if payload.quantity is not None:
        line.quantity = payload.quantity
    if payload.discount_pct is not None:
        line.discount_pct = payload.discount_pct

    # line_value is consistently price * quantity (pre-discount) elsewhere
    # in this codebase (see upsell.add_suggestion) - kept consistent here.
    line.line_value = product.price * line.quantity

    db.commit()
    db.refresh(line)

    return QuoteLineDetailResponse(
        id=line.id,
        product_id=line.product_id,
        product_name=product.name,
        quantity=line.quantity,
        discount_pct=line.discount_pct,
        line_value=line.line_value,
        is_recurring=line.is_recurring,
    )
