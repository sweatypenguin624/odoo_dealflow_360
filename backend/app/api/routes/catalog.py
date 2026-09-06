from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_internal_user, require_permission
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.pagination import Page, PageParams, paginate_query
from app.core.permissions import Permission
from app.models import (
    BillingInterval,
    Category,
    Customer,
    CustomerTier,
    Product,
    ProductPairing,
    ProductVariant,
    QuoteLine,
    Stock,
    SubscriptionPlan,
    User,
)
from app.schemas.catalog import (
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    PairingCreate,
    PairingOut,
    PairingUpdate,
    ProductCreate,
    ProductDetailOut,
    ProductOut,
    ProductPriceOut,
    ProductUpdate,
    SubscriptionPlanCreate,
    SubscriptionPlanOut,
    SubscriptionPlanUpdate,
    TierCreate,
    TierOut,
    TierUpdate,
    VariantCreate,
    VariantOut,
    VariantUpdate,
)
from app.services import audit_service, discount_service, pricing_service

router = APIRouter(tags=["catalog"])


# ---------------------------------------------------------------- helpers


def _product_out(product: Product) -> ProductOut:
    return ProductOut(
        id=product.id,
        sku=product.sku,
        name=product.name,
        description=product.description,
        category_id=product.category_id,
        category_name=product.category.name,
        cost=product.cost,
        price=product.price,
        unit=product.unit,
        tax_rate_pct=product.tax_rate_pct,
        product_type=product.product_type,
        is_stocked=product.is_stocked,
        unit_margin_pct=product.unit_margin_pct,
        is_active=product.is_active,
        is_archived=product.is_archived,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def _stock_available(db: Session, product_id: int) -> int:
    row = (
        db.query(func.coalesce(func.sum(Stock.quantity_on_hand - Stock.quantity_reserved), 0))
        .filter(Stock.product_id == product_id)
        .scalar()
    )
    return int(row or 0)


def _get_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product not found")
    return product


def _snapshot(product: Product) -> dict:
    return {
        "sku": product.sku,
        "name": product.name,
        "category_id": product.category_id,
        "cost": str(product.cost),
        "price": str(product.price),
        "tax_rate_pct": str(product.tax_rate_pct),
        "product_type": product.product_type.value,
        "is_stocked": product.is_stocked,
        "is_active": product.is_active,
        "is_archived": product.is_archived,
    }


# ---------------------------------------------------------------- categories


@router.get("/categories", response_model=Page[CategoryOut])
def list_categories(
    params: PageParams = Depends(),
    q: Optional[str] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.catalog_read)),
):
    query = db.query(Category)
    if q:
        query = query.filter(Category.name.ilike(f"%{q.strip()}%"))
    if not include_inactive:
        query = query.filter(Category.is_active.is_(True))
    rows, total = paginate_query(query.order_by(Category.name), params)
    counts = dict(
        db.query(Product.category_id, func.count(Product.id))
        .filter(Product.category_id.in_([c.id for c in rows] or [0]))
        .group_by(Product.category_id)
        .all()
    )
    items = [CategoryOut.model_validate(c).model_copy(update={"product_count": counts.get(c.id, 0)}) for c in rows]
    return Page.build(items, total, params)


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(
    payload: CategoryCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.catalog_manage))
):
    if db.query(Category).filter(func.lower(Category.name) == payload.name.strip().lower()).first():
        raise ConflictError(f"A category named '{payload.name}' already exists.")
    category = Category(**payload.model_dump())
    db.add(category)
    db.flush()
    audit_service.record(db, "category_created", actor=actor, entity_type="category", entity_id=category.id, after=payload.model_dump(mode="json"))
    db.commit()
    return CategoryOut.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.catalog_manage)),
):
    category = db.get(Category, category_id)
    if category is None:
        raise NotFoundError("Category not found")
    before = {"name": category.name, "max_discount_pct": str(category.max_discount_pct), "is_active": category.is_active}
    data = payload.model_dump(exclude_unset=True, exclude={"clear_max_discount"})
    for key, value in data.items():
        setattr(category, key, value)
    if payload.clear_max_discount:
        category.max_discount_pct = None
    after = {"name": category.name, "max_discount_pct": str(category.max_discount_pct), "is_active": category.is_active}
    audit_service.record(db, "category_updated", actor=actor, entity_type="category", entity_id=category.id, before=before, after=after)
    db.commit()
    return CategoryOut.model_validate(category)


# ---------------------------------------------------------------- products


@router.get("/products", response_model=Page[ProductOut])
def list_products(
    params: PageParams = Depends(),
    q: Optional[str] = Query(None, description="Search name or SKU"),
    category_id: Optional[int] = None,
    product_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    include_archived: bool = False,
    sort: str = Query("name", pattern="^(name|sku|price|created_at|-name|-sku|-price|-created_at)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.catalog_read)),
):
    query = db.query(Product).options(joinedload(Product.category))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if category_id is not None:
        query = query.filter(Product.category_id == category_id)
    if product_type:
        query = query.filter(Product.product_type == product_type)
    if is_active is not None:
        query = query.filter(Product.is_active.is_(is_active))
    if not include_archived:
        query = query.filter(Product.is_archived.is_(False))
    column = getattr(Product, sort.lstrip("-"))
    query = query.order_by(column.desc() if sort.startswith("-") else column.asc(), Product.id)
    rows, total = paginate_query(query, params)
    return Page.build([_product_out(p) for p in rows], total, params)


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(
    payload: ProductCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.catalog_manage))
):
    if db.get(Category, payload.category_id) is None:
        raise NotFoundError("Category not found")
    if db.query(Product).filter(Product.sku == payload.sku).first():
        raise ConflictError(f"SKU {payload.sku} is already in use.")
    if payload.cost > payload.price:
        raise ValidationError("Cost cannot exceed the selling price.")
    product = Product(**payload.model_dump())
    db.add(product)
    db.flush()
    audit_service.record(db, "product_created", actor=actor, entity_type="product", entity_id=product.id, after=_snapshot(product))
    db.commit()
    return _product_out(product)


@router.get("/products/{product_id}", response_model=ProductDetailOut)
def get_product(product_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.catalog_read))):
    product = _get_product(db, product_id)
    base = _product_out(product).model_dump()
    plans = db.query(SubscriptionPlan).filter(SubscriptionPlan.product_id == product.id).all()
    return ProductDetailOut(
        **base,
        variants=[VariantOut.model_validate(v) for v in product.variants],
        stock_available=_stock_available(db, product.id),
        subscription_plans=[
            {"id": p.id, "name": p.name, "interval": p.interval.value, "price_per_interval": float(p.price_per_interval), "is_active": p.is_active}
            for p in plans
        ],
    )


@router.get("/products/{product_id}/pricing", response_model=ProductPriceOut)
def get_product_pricing(
    product_id: int,
    customer_id: int,
    quantity: int = Query(1, ge=1),
    variant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.catalog_read)),
):
    product = _get_product(db, product_id)
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError("Customer not found")
    variant = None
    if variant_id is not None:
        variant = db.get(ProductVariant, variant_id)
        if variant is None or variant.product_id != product.id:
            raise NotFoundError("Variant not found on this product")
    resolved = pricing_service.resolve_price(db, product, customer, quantity, variant)
    limit, source = discount_service.allowed_discount_for(db, product, customer)
    return ProductPriceOut(
        product_id=product.id,
        variant_id=variant_id,
        unit_price=resolved.unit_price,
        unit_cost=resolved.unit_cost,
        currency=resolved.currency,
        price_source=resolved.source,
        allowed_discount_pct=limit,
        discount_limit_source=source,
        stock_available=_stock_available(db, product.id),
    )


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.catalog_manage)),
):
    product = _get_product(db, product_id)
    before = _snapshot(product)
    data = payload.model_dump(exclude_unset=True)
    if "sku" in data:
        data["sku"] = data["sku"].strip().upper()
        clash = db.query(Product).filter(Product.sku == data["sku"], Product.id != product.id).first()
        if clash:
            raise ConflictError(f"SKU {data['sku']} is already in use.")
    if "category_id" in data and db.get(Category, data["category_id"]) is None:
        raise NotFoundError("Category not found")
    for key, value in data.items():
        setattr(product, key, value)
    if product.cost > product.price:
        raise ValidationError("Cost cannot exceed the selling price.")
    audit_service.record(db, "product_updated", actor=actor, entity_type="product", entity_id=product.id, before=before, after=_snapshot(product))
    db.commit()
    return _product_out(product)


@router.post("/products/{product_id}/archive", response_model=ProductOut)
def archive_product(product_id: int, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.catalog_manage))):
    product = _get_product(db, product_id)
    referenced = db.query(QuoteLine.id).filter(QuoteLine.product_id == product.id).first() is not None
    product.is_archived = True
    product.is_active = False
    audit_service.record(
        db, "product_archived", actor=actor, entity_type="product", entity_id=product.id,
        reason="Archived (referenced by historical quotes; never deleted)" if referenced else "Archived",
    )
    db.commit()
    return _product_out(product)


@router.post("/products/{product_id}/restore", response_model=ProductOut)
def restore_product(product_id: int, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.catalog_manage))):
    product = _get_product(db, product_id)
    product.is_archived = False
    product.is_active = True
    audit_service.record(db, "product_restored", actor=actor, entity_type="product", entity_id=product.id)
    db.commit()
    return _product_out(product)


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.catalog_manage))):
    product = _get_product(db, product_id)
    if db.query(QuoteLine.id).filter(QuoteLine.product_id == product.id).first() is not None:
        raise ConflictError("This product is referenced by quotations and cannot be deleted. Archive it instead.")
    if db.query(Stock.id).filter(Stock.product_id == product.id).first() is not None:
        raise ConflictError("This product has stock records and cannot be deleted. Archive it instead.")
    audit_service.record(db, "product_deleted", actor=actor, entity_type="product", entity_id=product.id, before=_snapshot(product))
    db.delete(product)
    db.commit()


# ---------------------------------------------------------------- variants


@router.post("/products/{product_id}/variants", response_model=VariantOut, status_code=201)
def create_variant(
    product_id: int, payload: VariantCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.catalog_manage))
):
    product = _get_product(db, product_id)
    sku = payload.sku.strip().upper()
    if db.query(ProductVariant).filter(ProductVariant.sku == sku).first() or db.query(Product).filter(Product.sku == sku).first():
        raise ConflictError(f"SKU {sku} is already in use.")
    variant = ProductVariant(product_id=product.id, **{**payload.model_dump(), "sku": sku})
    db.add(variant)
    db.flush()
    audit_service.record(db, "variant_created", actor=actor, entity_type="product", entity_id=product.id, after=payload.model_dump(mode="json"))
    db.commit()
    return VariantOut.model_validate(variant)


@router.patch("/variants/{variant_id}", response_model=VariantOut)
def update_variant(
    variant_id: int, payload: VariantUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.catalog_manage))
):
    variant = db.get(ProductVariant, variant_id)
    if variant is None:
        raise NotFoundError("Variant not found")
    data = payload.model_dump(exclude_unset=True)
    if "sku" in data:
        data["sku"] = data["sku"].strip().upper()
        if db.query(ProductVariant).filter(ProductVariant.sku == data["sku"], ProductVariant.id != variant.id).first():
            raise ConflictError(f"SKU {data['sku']} is already in use.")
    for key, value in data.items():
        setattr(variant, key, value)
    audit_service.record(db, "variant_updated", actor=actor, entity_type="product", entity_id=variant.product_id, after=data if not data else {k: (str(v) if v is not None else None) for k, v in data.items()})
    db.commit()
    return VariantOut.model_validate(variant)


# ---------------------------------------------------------------- customer tiers


@router.get("/customer-tiers", response_model=list[TierOut])
def list_tiers(include_inactive: bool = False, db: Session = Depends(get_db), _: User = Depends(get_internal_user)):
    query = db.query(CustomerTier)
    if not include_inactive:
        query = query.filter(CustomerTier.is_active.is_(True))
    tiers = query.order_by(CustomerTier.sort_order, CustomerTier.name).all()
    counts = dict(db.query(Customer.tier_id, func.count(Customer.id)).group_by(Customer.tier_id).all())
    return [TierOut.model_validate(t).model_copy(update={"customer_count": counts.get(t.id, 0)}) for t in tiers]


@router.post("/customer-tiers", response_model=TierOut, status_code=201)
def create_tier(payload: TierCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.discount_rules_manage))):
    if db.query(CustomerTier).filter(func.lower(CustomerTier.name) == payload.name.strip().lower()).first():
        raise ConflictError(f"A tier named '{payload.name}' already exists.")
    tier = CustomerTier(**payload.model_dump())
    db.add(tier)
    db.flush()
    audit_service.record(db, "tier_created", actor=actor, entity_type="customer_tier", entity_id=tier.id, after=payload.model_dump(mode="json"))
    db.commit()
    return TierOut.model_validate(tier)


@router.patch("/customer-tiers/{tier_id}", response_model=TierOut)
def update_tier(
    tier_id: int, payload: TierUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.discount_rules_manage))
):
    tier = db.get(CustomerTier, tier_id)
    if tier is None:
        raise NotFoundError("Tier not found")
    before = {"name": tier.name, "max_discount_pct": str(tier.max_discount_pct), "is_active": tier.is_active}
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(tier, key, value)
    after = {"name": tier.name, "max_discount_pct": str(tier.max_discount_pct), "is_active": tier.is_active}
    audit_service.record(db, "tier_updated", actor=actor, entity_type="customer_tier", entity_id=tier.id, before=before, after=after)
    db.commit()
    return TierOut.model_validate(tier)


# ---------------------------------------------------------------- subscription plans


def _plan_out(plan: SubscriptionPlan) -> SubscriptionPlanOut:
    return SubscriptionPlanOut(
        id=plan.id,
        name=plan.name,
        product_id=plan.product_id,
        product_name=plan.product.name if plan.product else "",
        interval=plan.interval.value,
        price_per_interval=plan.price_per_interval,
        proration_enabled=plan.proration_enabled,
        is_active=plan.is_active,
    )


@router.get("/subscription-plans", response_model=Page[SubscriptionPlanOut])
def list_subscription_plans(
    params: PageParams = Depends(),
    product_id: Optional[int] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.catalog_read)),
):
    query = db.query(SubscriptionPlan).options(joinedload(SubscriptionPlan.product))
    if product_id is not None:
        query = query.filter(SubscriptionPlan.product_id == product_id)
    if not include_inactive:
        query = query.filter(SubscriptionPlan.is_active.is_(True))
    rows, total = paginate_query(query.order_by(SubscriptionPlan.name), params)
    return Page.build([_plan_out(p) for p in rows], total, params)


@router.post("/subscription-plans", response_model=SubscriptionPlanOut, status_code=201)
def create_subscription_plan(
    payload: SubscriptionPlanCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.catalog_manage))
):
    product = _get_product(db, payload.product_id)
    try:
        interval = BillingInterval(payload.interval)
    except ValueError:
        raise ValidationError("interval must be monthly, quarterly or yearly")
    plan = SubscriptionPlan(
        name=payload.name,
        product_id=product.id,
        interval=interval,
        price_per_interval=payload.price_per_interval,
        proration_enabled=payload.proration_enabled,
        is_active=payload.is_active,
    )
    db.add(plan)
    db.flush()
    audit_service.record(db, "subscription_plan_created", actor=actor, entity_type="subscription_plan", entity_id=plan.id, after=payload.model_dump(mode="json"))
    db.commit()
    return _plan_out(plan)


@router.patch("/subscription-plans/{plan_id}", response_model=SubscriptionPlanOut)
def update_subscription_plan(
    plan_id: int, payload: SubscriptionPlanUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.catalog_manage))
):
    plan = db.get(SubscriptionPlan, plan_id)
    if plan is None:
        raise NotFoundError("Subscription plan not found")
    data = payload.model_dump(exclude_unset=True)
    if "interval" in data:
        try:
            data["interval"] = BillingInterval(data["interval"])
        except ValueError:
            raise ValidationError("interval must be monthly, quarterly or yearly")
    for key, value in data.items():
        setattr(plan, key, value)
    audit_service.record(db, "subscription_plan_updated", actor=actor, entity_type="subscription_plan", entity_id=plan.id, after=payload.model_dump(mode="json", exclude_unset=True))
    db.commit()
    return _plan_out(plan)


# ---------------------------------------------------------------- product pairings


def _pairing_out(p: ProductPairing) -> PairingOut:
    return PairingOut(
        id=p.id,
        base_product_id=p.base_product_id,
        base_product_name=p.base_product.name if p.base_product else "",
        suggested_product_id=p.suggested_product_id,
        suggested_product_name=p.suggested_product.name if p.suggested_product else "",
        co_purchase_score=p.co_purchase_score,
        is_promoted=p.is_promoted,
        promotion_label=p.promotion_label,
        promotion_start=p.promotion_start,
        promotion_end=p.promotion_end,
        is_active=p.is_active,
    )


@router.get("/product-pairings", response_model=Page[PairingOut])
def list_pairings(
    params: PageParams = Depends(),
    base_product_id: Optional[int] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.catalog_read)),
):
    query = db.query(ProductPairing).options(joinedload(ProductPairing.base_product), joinedload(ProductPairing.suggested_product))
    if base_product_id is not None:
        query = query.filter(ProductPairing.base_product_id == base_product_id)
    if q:
        like = f"%{q.strip()}%"
        Base = Product
        query = query.join(Base, ProductPairing.base_product_id == Base.id).filter(Base.name.ilike(like))
    rows, total = paginate_query(query.order_by(ProductPairing.base_product_id, ProductPairing.co_purchase_score.desc()), params)
    return Page.build([_pairing_out(p) for p in rows], total, params)


@router.post("/product-pairings", response_model=PairingOut, status_code=201)
def create_pairing(payload: PairingCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.catalog_manage))):
    if payload.base_product_id == payload.suggested_product_id:
        raise ValidationError("A product cannot be paired with itself.")
    _get_product(db, payload.base_product_id)
    _get_product(db, payload.suggested_product_id)
    exists = (
        db.query(ProductPairing)
        .filter(ProductPairing.base_product_id == payload.base_product_id, ProductPairing.suggested_product_id == payload.suggested_product_id)
        .first()
    )
    if exists:
        raise ConflictError("This pairing already exists.")
    pairing = ProductPairing(**payload.model_dump())
    db.add(pairing)
    db.flush()
    audit_service.record(db, "pairing_created", actor=actor, entity_type="product_pairing", entity_id=pairing.id, after=payload.model_dump(mode="json"))
    db.commit()
    return _pairing_out(pairing)


@router.patch("/product-pairings/{pairing_id}", response_model=PairingOut)
def update_pairing(
    pairing_id: int, payload: PairingUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.catalog_manage))
):
    pairing = db.get(ProductPairing, pairing_id)
    if pairing is None:
        raise NotFoundError("Pairing not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(pairing, key, value)
    audit_service.record(db, "pairing_updated", actor=actor, entity_type="product_pairing", entity_id=pairing.id, after=payload.model_dump(mode="json", exclude_unset=True))
    db.commit()
    return _pairing_out(pairing)


@router.delete("/product-pairings/{pairing_id}", status_code=204)
def delete_pairing(pairing_id: int, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.catalog_manage))):
    pairing = db.get(ProductPairing, pairing_id)
    if pairing is None:
        raise NotFoundError("Pairing not found")
    audit_service.record(db, "pairing_deleted", actor=actor, entity_type="product_pairing", entity_id=pairing.id)
    db.delete(pairing)
    db.commit()
