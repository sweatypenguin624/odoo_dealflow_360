"""Server-side price resolution.

The price a quote line uses is never trusted from the client. It is
resolved here from (most specific first):
  1. an active price list scoped to the customer's tier, matching product
     (+ variant) with the largest satisfied min_quantity, highest priority
  2. an active un-scoped (global) price list, same matching
  3. the variant's own price, else the product list price
The resolved price is snapshotted onto the quote line, so later catalog
changes never rewrite historical quotes.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core.money import D, money
from app.models import Customer, PriceList, PriceListItem, Product, ProductVariant


@dataclass
class ResolvedPrice:
    unit_price: Decimal
    unit_cost: Decimal
    source: str
    price_list_id: Optional[int] = None
    currency: str = "USD"


def _list_active(price_list: PriceList, as_of: date) -> bool:
    if not price_list.is_active:
        return False
    if price_list.valid_from and as_of < price_list.valid_from:
        return False
    if price_list.valid_to and as_of > price_list.valid_to:
        return False
    return True


def resolve_price(
    db: Session,
    product: Product,
    customer: Optional[Customer],
    quantity: int = 1,
    variant: Optional[ProductVariant] = None,
    as_of: Optional[date] = None,
) -> ResolvedPrice:
    as_of = as_of or date.today()
    unit_cost = money(variant.effective_cost if variant else product.cost)
    base_price = money(variant.effective_price if variant else product.price)
    currency = customer.currency if customer else "USD"

    query = (
        db.query(PriceListItem, PriceList)
        .join(PriceList, PriceListItem.price_list_id == PriceList.id)
        .filter(PriceListItem.product_id == product.id, PriceListItem.min_quantity <= max(1, quantity))
    )
    if variant is not None:
        query = query.filter((PriceListItem.variant_id == variant.id) | (PriceListItem.variant_id.is_(None)))
    else:
        query = query.filter(PriceListItem.variant_id.is_(None))
    rows = [(item, pl) for item, pl in query.all() if _list_active(pl, as_of)]

    tier_id = customer.tier_id if customer else None
    candidates = []
    for item, pl in rows:
        if pl.tier_id is not None and pl.tier_id != tier_id:
            continue
        specificity = (
            1 if pl.tier_id is not None else 0,
            1 if (variant is not None and item.variant_id is not None) else 0,
            item.min_quantity,
            pl.priority,
        )
        candidates.append((specificity, item, pl))
    if candidates:
        candidates.sort(key=lambda c: c[0], reverse=True)
        _, item, pl = candidates[0]
        label = f"Price list '{pl.name}'" + (f" ({pl.tier.name} tier)" if pl.tier_id else "")
        if item.min_quantity > 1:
            label += f", {item.min_quantity}+ units"
        return ResolvedPrice(money(item.unit_price), unit_cost, label, pl.id, pl.currency)

    source = "Variant price" if variant is not None and variant.price is not None else "List price"
    return ResolvedPrice(base_price, unit_cost, source, None, currency)
