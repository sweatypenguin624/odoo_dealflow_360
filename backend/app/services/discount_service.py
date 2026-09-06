"""Resolve the discount ceiling that governs each quote line and build the
risk-engine inputs. This is the single place that knows about DiscountRule
precedence, so the risk engine stays a reusable pure function."""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.money import D
from app.models import Customer, DiscountRule, DiscountRuleScope, Product, Quote, QuoteLine
from app.services.risk_engine import LineInput


def _rule_active(rule: DiscountRule, as_of: date) -> bool:
    if not rule.is_active:
        return False
    if rule.valid_from and as_of < rule.valid_from:
        return False
    if rule.valid_to and as_of > rule.valid_to:
        return False
    return True


def load_active_rules(db: Session, as_of: Optional[date] = None) -> List[DiscountRule]:
    as_of = as_of or date.today()
    return [r for r in db.query(DiscountRule).all() if _rule_active(r, as_of)]


def resolve_rule_limit(
    rules: List[DiscountRule], product: Product, customer: Customer
) -> Tuple[Optional[Decimal], Optional[str]]:
    """Return (override_limit, label) from the most specific matching rule.

    Specificity: product > tier×category > (tier-only / category-only
    rules act as overrides of the base ceilings and are folded into the
    tier / category values by the caller)."""
    product_rules = [r for r in rules if r.scope == DiscountRuleScope.product and r.product_id == product.id]
    if product_rules:
        r = max(product_rules, key=lambda r: r.priority)
        return D(r.max_discount_pct), f"Rule '{r.name}' for {product.name}"
    combo = [
        r
        for r in rules
        if r.scope == DiscountRuleScope.tier_category
        and r.tier_id == customer.tier_id
        and r.category_id == product.category_id
    ]
    if combo:
        r = max(combo, key=lambda r: r.priority)
        return D(r.max_discount_pct), f"{customer.tier.name} tier on {product.category.name}"
    return None, None


def effective_tier_limit(rules: List[DiscountRule], customer: Customer) -> Decimal:
    tier_rules = [r for r in rules if r.scope == DiscountRuleScope.tier and r.tier_id == customer.tier_id]
    if tier_rules:
        return D(max(tier_rules, key=lambda r: r.priority).max_discount_pct)
    return D(customer.tier.max_discount_pct)


def effective_category_limit(rules: List[DiscountRule], product: Product) -> Optional[Decimal]:
    cat_rules = [r for r in rules if r.scope == DiscountRuleScope.category and r.category_id == product.category_id]
    if cat_rules:
        return D(max(cat_rules, key=lambda r: r.priority).max_discount_pct)
    return D(product.category.max_discount_pct) if product.category.max_discount_pct is not None else None


def build_line_inputs(db: Session, quote: Quote, as_of: Optional[date] = None) -> List[LineInput]:
    customer = quote.customer
    rules = load_active_rules(db, as_of)
    tier_limit = effective_tier_limit(rules, customer)
    inputs: List[LineInput] = []
    for line in quote.lines:
        product = line.product
        override, source = resolve_rule_limit(rules, product, customer)
        inputs.append(
            LineInput(
                line_id=line.id,
                discount_pct=D(line.discount_pct),
                line_value=D(line.line_value),
                category_max_discount_pct=effective_category_limit(rules, product),
                tier_max_discount_pct=tier_limit,
                override_limit=override,
                limit_source=source,
                label=line.description or product.name,
                category_name=product.category.name,
                tier_name=customer.tier.name,
            )
        )
    return inputs


def allowed_discount_for(db: Session, product: Product, customer: Customer) -> Tuple[Decimal, str]:
    """What the UI shows in the builder before a line is even saved."""
    from app.services.risk_engine import resolve_applicable_limit

    rules = load_active_rules(db)
    override, source = resolve_rule_limit(rules, product, customer)
    probe = LineInput(
        line_id=0,
        discount_pct=0,
        line_value=0,
        category_max_discount_pct=effective_category_limit(rules, product),
        tier_max_discount_pct=effective_tier_limit(rules, customer),
        override_limit=override,
        limit_source=source,
        category_name=product.category.name,
        tier_name=customer.tier.name,
    )
    return resolve_applicable_limit(probe)
