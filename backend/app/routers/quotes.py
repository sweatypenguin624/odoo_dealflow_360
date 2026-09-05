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
    return quotes


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
