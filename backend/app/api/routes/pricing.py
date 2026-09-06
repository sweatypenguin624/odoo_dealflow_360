from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_permission
from app.core.errors import NotFoundError, ValidationError
from app.core.pagination import Page, PageParams, paginate_query
from app.core.permissions import Permission
from app.models import (
    ApprovalRule,
    Category,
    CustomerTier,
    DiscountRule,
    PriceList,
    PriceListItem,
    Product,
    ProductVariant,
    User,
)
from app.schemas.pricing import (
    ApprovalRuleCreate,
    ApprovalRuleOut,
    ApprovalRuleUpdate,
    DiscountRuleCreate,
    DiscountRuleOut,
    DiscountRuleUpdate,
    PriceListCreate,
    PriceListDetailOut,
    PriceListItemIn,
    PriceListItemOut,
    PriceListOut,
    PriceListUpdate,
    RiskPolicyOut,
)
from app.services import audit_service, settings_service

router = APIRouter(tags=["pricing"])


# ---------------------------------------------------------------- price lists


def _price_list_out(pl: PriceList) -> PriceListOut:
    return PriceListOut(
        id=pl.id,
        name=pl.name,
        currency=pl.currency,
        tier_id=pl.tier_id,
        tier_name=pl.tier.name if pl.tier else None,
        valid_from=pl.valid_from,
        valid_to=pl.valid_to,
        priority=pl.priority,
        is_active=pl.is_active,
        item_count=len(pl.items),
    )


def _item_out(item: PriceListItem) -> PriceListItemOut:
    return PriceListItemOut(
        id=item.id,
        product_id=item.product_id,
        product_name=item.product.name if item.product else "",
        product_sku=item.product.sku if item.product else None,
        variant_id=item.variant_id,
        min_quantity=item.min_quantity,
        unit_price=item.unit_price,
    )


def _validate_item(db: Session, item: PriceListItemIn) -> None:
    if db.get(Product, item.product_id) is None:
        raise NotFoundError(f"Product {item.product_id} not found")
    if item.variant_id is not None:
        variant = db.get(ProductVariant, item.variant_id)
        if variant is None or variant.product_id != item.product_id:
            raise NotFoundError(f"Variant {item.variant_id} not found on product {item.product_id}")


@router.get("/price-lists", response_model=Page[PriceListOut])
def list_price_lists(
    params: PageParams = Depends(),
    tier_id: Optional[int] = None,
    include_inactive: bool = True,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.catalog_read)),
):
    query = db.query(PriceList).options(joinedload(PriceList.tier), joinedload(PriceList.items))
    if tier_id is not None:
        query = query.filter(PriceList.tier_id == tier_id)
    if not include_inactive:
        query = query.filter(PriceList.is_active.is_(True))
    rows, total = paginate_query(query.order_by(PriceList.priority.desc(), PriceList.name), params)
    return Page.build([_price_list_out(pl) for pl in rows], total, params)


@router.post("/price-lists", response_model=PriceListDetailOut, status_code=201)
def create_price_list(payload: PriceListCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.pricing_manage))):
    if payload.tier_id is not None and db.get(CustomerTier, payload.tier_id) is None:
        raise NotFoundError("Tier not found")
    if payload.valid_from and payload.valid_to and payload.valid_to < payload.valid_from:
        raise ValidationError("valid_to must be on or after valid_from")
    for item in payload.items:
        _validate_item(db, item)
    pl = PriceList(**payload.model_dump(exclude={"items"}))
    db.add(pl)
    db.flush()
    for item in payload.items:
        db.add(PriceListItem(price_list_id=pl.id, **item.model_dump()))
    db.flush()
    audit_service.record(db, "price_list_created", actor=actor, entity_type="price_list", entity_id=pl.id, after=payload.model_dump(mode="json"))
    db.commit()
    db.refresh(pl)
    return PriceListDetailOut(**_price_list_out(pl).model_dump(), items=[_item_out(i) for i in pl.items])


@router.get("/price-lists/{price_list_id}", response_model=PriceListDetailOut)
def get_price_list(price_list_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.catalog_read))):
    pl = db.get(PriceList, price_list_id)
    if pl is None:
        raise NotFoundError("Price list not found")
    return PriceListDetailOut(**_price_list_out(pl).model_dump(), items=[_item_out(i) for i in pl.items])


@router.patch("/price-lists/{price_list_id}", response_model=PriceListDetailOut)
def update_price_list(
    price_list_id: int, payload: PriceListUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.pricing_manage))
):
    pl = db.get(PriceList, price_list_id)
    if pl is None:
        raise NotFoundError("Price list not found")
    data = payload.model_dump(exclude_unset=True, exclude={"clear_tier"})
    if "tier_id" in data and data["tier_id"] is not None and db.get(CustomerTier, data["tier_id"]) is None:
        raise NotFoundError("Tier not found")
    for key, value in data.items():
        setattr(pl, key, value)
    if payload.clear_tier:
        pl.tier_id = None
    audit_service.record(db, "price_list_updated", actor=actor, entity_type="price_list", entity_id=pl.id, after=payload.model_dump(mode="json", exclude_unset=True))
    db.commit()
    db.refresh(pl)
    return PriceListDetailOut(**_price_list_out(pl).model_dump(), items=[_item_out(i) for i in pl.items])


@router.put("/price-lists/{price_list_id}/items", response_model=PriceListDetailOut, summary="Replace all items")
def replace_price_list_items(
    price_list_id: int, items: list[PriceListItemIn], db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.pricing_manage))
):
    pl = db.get(PriceList, price_list_id)
    if pl is None:
        raise NotFoundError("Price list not found")
    for item in items:
        _validate_item(db, item)
    seen = set()
    for item in items:
        key = (item.product_id, item.variant_id, item.min_quantity)
        if key in seen:
            raise ValidationError(f"Duplicate item for product {item.product_id} at min quantity {item.min_quantity}")
        seen.add(key)
    db.query(PriceListItem).filter(PriceListItem.price_list_id == pl.id).delete(synchronize_session=False)
    for item in items:
        db.add(PriceListItem(price_list_id=pl.id, **item.model_dump()))
    audit_service.record(db, "price_list_items_replaced", actor=actor, entity_type="price_list", entity_id=pl.id, after={"item_count": len(items)})
    db.commit()
    db.refresh(pl)
    return PriceListDetailOut(**_price_list_out(pl).model_dump(), items=[_item_out(i) for i in pl.items])


@router.post("/price-lists/{price_list_id}/items", response_model=PriceListItemOut, status_code=201)
def add_price_list_item(
    price_list_id: int, payload: PriceListItemIn, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.pricing_manage))
):
    pl = db.get(PriceList, price_list_id)
    if pl is None:
        raise NotFoundError("Price list not found")
    _validate_item(db, payload)
    existing = (
        db.query(PriceListItem)
        .filter(
            PriceListItem.price_list_id == pl.id,
            PriceListItem.product_id == payload.product_id,
            PriceListItem.variant_id == payload.variant_id,
            PriceListItem.min_quantity == payload.min_quantity,
        )
        .first()
    )
    if existing:
        existing.unit_price = payload.unit_price
        item = existing
    else:
        item = PriceListItem(price_list_id=pl.id, **payload.model_dump())
        db.add(item)
    db.flush()
    audit_service.record(db, "price_list_item_saved", actor=actor, entity_type="price_list", entity_id=pl.id, after=payload.model_dump(mode="json"))
    db.commit()
    db.refresh(item)
    return _item_out(item)


@router.delete("/price-lists/{price_list_id}/items/{item_id}", status_code=204)
def delete_price_list_item(
    price_list_id: int, item_id: int, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.pricing_manage))
):
    item = db.get(PriceListItem, item_id)
    if item is None or item.price_list_id != price_list_id:
        raise NotFoundError("Price list item not found")
    audit_service.record(db, "price_list_item_deleted", actor=actor, entity_type="price_list", entity_id=price_list_id, before={"product_id": item.product_id})
    db.delete(item)
    db.commit()


# ---------------------------------------------------------------- discount rules


def _rule_out(r: DiscountRule) -> DiscountRuleOut:
    return DiscountRuleOut(
        id=r.id,
        name=r.name,
        scope=r.scope,
        tier_id=r.tier_id,
        tier_name=r.tier.name if r.tier else None,
        category_id=r.category_id,
        category_name=r.category.name if r.category else None,
        product_id=r.product_id,
        product_name=r.product.name if r.product else None,
        max_discount_pct=r.max_discount_pct,
        valid_from=r.valid_from,
        valid_to=r.valid_to,
        priority=r.priority,
        is_active=r.is_active,
    )


@router.get("/discount-rules", response_model=Page[DiscountRuleOut])
def list_discount_rules(
    params: PageParams = Depends(),
    scope: Optional[str] = None,
    include_inactive: bool = True,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.catalog_read)),
):
    query = db.query(DiscountRule)
    if scope:
        query = query.filter(DiscountRule.scope == scope)
    if not include_inactive:
        query = query.filter(DiscountRule.is_active.is_(True))
    rows, total = paginate_query(query.order_by(DiscountRule.scope, DiscountRule.priority.desc(), DiscountRule.name), params)
    return Page.build([_rule_out(r) for r in rows], total, params)


def _validate_rule_targets(db: Session, tier_id, category_id, product_id):
    if tier_id is not None and db.get(CustomerTier, tier_id) is None:
        raise NotFoundError("Tier not found")
    if category_id is not None and db.get(Category, category_id) is None:
        raise NotFoundError("Category not found")
    if product_id is not None and db.get(Product, product_id) is None:
        raise NotFoundError("Product not found")


@router.post("/discount-rules", response_model=DiscountRuleOut, status_code=201)
def create_discount_rule(
    payload: DiscountRuleCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.discount_rules_manage))
):
    _validate_rule_targets(db, payload.tier_id, payload.category_id, payload.product_id)
    rule = DiscountRule(**payload.model_dump())
    db.add(rule)
    db.flush()
    audit_service.record(db, "discount_rule_created", actor=actor, entity_type="discount_rule", entity_id=rule.id, after=payload.model_dump(mode="json"))
    db.commit()
    return _rule_out(rule)


@router.patch("/discount-rules/{rule_id}", response_model=DiscountRuleOut)
def update_discount_rule(
    rule_id: int, payload: DiscountRuleUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.discount_rules_manage))
):
    rule = db.get(DiscountRule, rule_id)
    if rule is None:
        raise NotFoundError("Discount rule not found")
    before = {"max_discount_pct": str(rule.max_discount_pct), "is_active": rule.is_active}
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    audit_service.record(
        db, "discount_rule_updated", actor=actor, entity_type="discount_rule", entity_id=rule.id, before=before,
        after={"max_discount_pct": str(rule.max_discount_pct), "is_active": rule.is_active},
    )
    db.commit()
    return _rule_out(rule)


@router.delete("/discount-rules/{rule_id}", status_code=204)
def delete_discount_rule(rule_id: int, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.discount_rules_manage))):
    rule = db.get(DiscountRule, rule_id)
    if rule is None:
        raise NotFoundError("Discount rule not found")
    audit_service.record(db, "discount_rule_deleted", actor=actor, entity_type="discount_rule", entity_id=rule.id, before={"name": rule.name})
    db.delete(rule)
    db.commit()


# ---------------------------------------------------------------- approval rules


@router.get("/approval-rules", response_model=list[ApprovalRuleOut])
def list_approval_rules(db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.approval_read))):
    return [ApprovalRuleOut.model_validate(r) for r in db.query(ApprovalRule).order_by(ApprovalRule.min_points_over).all()]


@router.get("/approval-rules/policy", response_model=RiskPolicyOut, summary="Effective thresholds used by the risk engine right now")
def get_risk_policy(db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.approval_read))):
    policy = settings_service.risk_policy(db)
    return RiskPolicyOut(**policy.__dict__)


@router.post("/approval-rules", response_model=ApprovalRuleOut, status_code=201)
def create_approval_rule(
    payload: ApprovalRuleCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.approval_rules_manage))
):
    rule = ApprovalRule(**payload.model_dump())
    db.add(rule)
    db.flush()
    audit_service.record(db, "approval_rule_created", actor=actor, entity_type="approval_rule", entity_id=rule.id, after=payload.model_dump(mode="json"))
    db.commit()
    return ApprovalRuleOut.model_validate(rule)


@router.patch("/approval-rules/{rule_id}", response_model=ApprovalRuleOut)
def update_approval_rule(
    rule_id: int, payload: ApprovalRuleUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.approval_rules_manage))
):
    rule = db.get(ApprovalRule, rule_id)
    if rule is None:
        raise NotFoundError("Approval rule not found")
    data = payload.model_dump(exclude_unset=True, exclude={"clear_min_excess_amount"})
    for key, value in data.items():
        setattr(rule, key, value)
    if payload.clear_min_excess_amount:
        rule.min_excess_amount = None
    audit_service.record(db, "approval_rule_updated", actor=actor, entity_type="approval_rule", entity_id=rule.id, after=payload.model_dump(mode="json", exclude_unset=True))
    db.commit()
    return ApprovalRuleOut.model_validate(rule)


@router.delete("/approval-rules/{rule_id}", status_code=204)
def delete_approval_rule(rule_id: int, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.approval_rules_manage))):
    rule = db.get(ApprovalRule, rule_id)
    if rule is None:
        raise NotFoundError("Approval rule not found")
    audit_service.record(db, "approval_rule_deleted", actor=actor, entity_type="approval_rule", entity_id=rule.id, before={"name": rule.name})
    db.delete(rule)
    db.commit()
