"""Typed system settings with environment defaults, plus the risk policy
derived from the configurable approval rules."""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.core.money import D
from app.models import ApprovalLevel, ApprovalRule, SystemSetting, User
from app.services.risk_engine import RiskPolicy

# key -> (type, default, description)
SETTING_DEFINITIONS: Dict[str, tuple] = {
    "stall_threshold_days": ("int", settings.stall_threshold_days, "Days without activity before an open quote is flagged as stalled"),
    "discount_anomaly_multiplier": ("float", settings.discount_anomaly_multiplier, "A quote is anomalous when its discount exceeds the rep's average × this multiplier"),
    "discount_anomaly_min_gap_points": ("float", 4.0, "Minimum percentage-point gap above the rep's average before a discount is anomalous"),
    "delivery_slippage_warning_days": ("int", settings.delivery_slippage_warning_days, "Days late before delivery slippage is a warning"),
    "delivery_slippage_critical_days": ("int", settings.delivery_slippage_critical_days, "Days late before delivery slippage is critical"),
    "approval_aging_days": ("int", settings.approval_aging_days, "Days an approval may wait before it is flagged"),
    "negotiation_aging_days": ("int", settings.negotiation_aging_days, "Days without a customer response before a negotiation is flagged"),
    "payment_overdue_grace_days": ("int", settings.payment_overdue_grace_days, "Grace days after due date before an invoice is overdue"),
    "invoice_due_days": ("int", settings.invoice_due_days, "Default payment terms for generated invoices"),
    "quote_valid_days": ("int", settings.quote_valid_days, "Default validity window for new quotations"),
    "default_currency": ("str", settings.default_currency, "Currency used for new quotes and price lists"),
    "upsell_min_margin_pct": ("float", 10.0, "Minimum unit margin for a product to be suggested as an upsell"),
    "upsell_max_suggestions": ("int", 5, "Maximum upsell suggestions shown in the quote builder"),
    "portal_token_hours": ("int", settings.portal_token_hours, "Lifetime of a customer portal link"),
    "approval_expiry_days": ("int", 14, "Pending approvals older than this expire automatically"),
}

_CASTERS = {
    "int": int,
    "float": float,
    "bool": lambda v: str(v).lower() in ("1", "true", "yes", "on"),
    "str": str,
}


def get_setting(db: Session, key: str) -> Any:
    value_type, default, _ = SETTING_DEFINITIONS[key]
    row = db.get(SystemSetting, key)
    if row is None:
        return default
    return _CASTERS[value_type](row.value)


def all_settings(db: Session) -> list[dict]:
    rows = {r.key: r for r in db.query(SystemSetting).all()}
    out = []
    for key, (value_type, default, description) in SETTING_DEFINITIONS.items():
        row = rows.get(key)
        out.append(
            {
                "key": key,
                "value": _CASTERS[value_type](row.value) if row else default,
                "value_type": value_type,
                "default": default,
                "description": description,
                "updated_at": row.updated_at if row else None,
            }
        )
    return out


def set_setting(db: Session, key: str, value: Any, user: Optional[User] = None) -> dict:
    if key not in SETTING_DEFINITIONS:
        from app.core.errors import NotFoundError

        raise NotFoundError(f"Unknown setting '{key}'")
    value_type, _, _ = SETTING_DEFINITIONS[key]
    try:
        typed = _CASTERS[value_type](value)
    except (TypeError, ValueError):
        from app.core.errors import ValidationError

        raise ValidationError(f"Setting '{key}' expects a {value_type} value")
    row = db.get(SystemSetting, key)
    if row is None:
        row = SystemSetting(key=key, value=str(typed), value_type=value_type)
        db.add(row)
    else:
        row.value = str(typed)
    row.updated_by_user_id = user.id if user else None
    db.flush()
    return {"key": key, "value": typed, "value_type": value_type}


def _rule_active(rule: ApprovalRule, as_of: date) -> bool:
    if not rule.is_active:
        return False
    if rule.valid_from and as_of < rule.valid_from:
        return False
    if rule.valid_to and as_of > rule.valid_to:
        return False
    return True


def risk_policy(db: Session, as_of: Optional[date] = None) -> RiskPolicy:
    """Build the risk policy from configured approval rules.

    Falls back to the engine defaults (5 / 15 points) when no rule for a
    level is configured, so a fresh database still behaves sensibly.
    """
    as_of = as_of or date.today()
    rules = [r for r in db.query(ApprovalRule).all() if _rule_active(r, as_of)]
    policy = RiskPolicy()
    manager = [r for r in rules if r.approval_level == ApprovalLevel.manager]
    finance = [r for r in rules if r.approval_level == ApprovalLevel.manager_then_finance]
    if manager:
        policy.manager_threshold = min(D(r.min_points_over) for r in manager)
        amounts = [D(r.min_excess_amount) for r in manager if r.min_excess_amount is not None]
        policy.manager_excess_amount = min(amounts) if amounts else None
    if finance:
        policy.finance_threshold = min(D(r.min_points_over) for r in finance)
        amounts = [D(r.min_excess_amount) for r in finance if r.min_excess_amount is not None]
        policy.finance_excess_amount = min(amounts) if amounts else None
    if policy.finance_threshold < policy.manager_threshold:
        policy.manager_threshold = policy.finance_threshold
    return policy


def approval_expiry_days(db: Session, level: str) -> Optional[int]:
    rules = db.query(ApprovalRule).filter(ApprovalRule.is_active.is_(True)).all()
    matching = [r.expires_after_days for r in rules if r.approval_level.value == level and r.expires_after_days]
    if matching:
        return min(matching)
    return get_setting(db, "approval_expiry_days")
