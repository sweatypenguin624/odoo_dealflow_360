"""Deterministic, production-like seed.

Everything flows through the real domain services (quotes are submitted,
approved, sent, negotiated, confirmed, reserved, shipped, invoiced and
paid by the same code the API uses), then each quote's timeline is
back-dated so the dataset spans the last eight months. Re-running with
the same seed produces the same dataset.

    python -m app.seed             # seed only if the database is empty
    python -m app.seed --fresh     # wipe every table and reseed (refused in production unless --force)
"""

from __future__ import annotations

import logging
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import Role
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import (
    ApprovalAction,
    ApprovalRequest,
    ApprovalRule,
    AuditLog,
    BillingEvent,
    Category,
    CounterProposal,
    Customer,
    CustomerTier,
    DealHealthAlert,
    DiscountRule,
    EmailMessage,
    FulfillmentPlan,
    Invoice,
    LineComment,
    Notification,
    Payment,
    PriceList,
    PriceListItem,
    Product,
    ProductPairing,
    ProductType,
    ProductVariant,
    Quote,
    QuoteLine,
    QuoteRevision,
    QuoteStatus,
    Shipment,
    Subscription,
    SubscriptionPlan,
    User,
    Warehouse,
)
from app.schemas.quotes import QuoteLineCreate
from app.seed import data as D
from app.services import (
    approval_service,
    deal_health_service,
    fulfillment_service,
    inventory_service,
    invoice_service,
    portal_service,
    quote_service,
    subscription_service,
)
from app.core.errors import StateTransitionError
from app.services.inventory_service import StockShortage
from app.services.numbering import next_number

logger = logging.getLogger("dealflow.seed")
NOW = datetime.now(timezone.utc)
TODAY = NOW.date()


class Seeder:
    def __init__(self, db: Session, seed: int = 42):
        self.db = db
        self.rng = random.Random(seed)
        self.users: Dict[str, User] = {}
        self.reps: List[User] = []
        self.managers: List[User] = []
        self.finance: List[User] = []
        self.admin: Optional[User] = None
        self.tiers: Dict[str, CustomerTier] = {}
        self.categories: Dict[str, Category] = {}
        self.products: Dict[str, Product] = {}
        self.plans: Dict[str, List[SubscriptionPlan]] = {}
        self.customers: List[Customer] = []
        self.warehouses: List[Warehouse] = []
        self.stats: Dict[str, int] = {}
        # per-rep discounting style: (mean %, spread) — Marcus is the outlier
        self.rep_style: Dict[int, tuple] = {}

    # ------------------------------------------------------------------ helpers

    def pick(self, seq, k=1):
        return self.rng.sample(list(seq), k)

    def one(self, seq):
        return self.rng.choice(list(seq))

    def days_ago(self, lo: int, hi: int) -> datetime:
        return NOW - timedelta(days=self.rng.randint(lo, hi), hours=self.rng.randint(0, 23), minutes=self.rng.randint(0, 59))

    def quote(self, quote_id: int) -> Quote:
        self.db.flush()
        return quote_service.load_quote(self.db, quote_id)

    # ------------------------------------------------------------------ 1. users

    def seed_users(self):
        hashed = hash_password(D.DEMO_PASSWORD)
        for email, name, role, team in D.USERS:
            user = User(email=email, full_name=name, hashed_password=hashed, role=Role(role), team=team, is_active=True)
            self.db.add(user)
            self.users[email] = user
        self.db.flush()
        self.admin = self.users["admin@dealflow360.demo"]
        self.reps = [u for u in self.users.values() if u.role == Role.sales_rep]
        self.managers = [u for u in self.users.values() if u.role == Role.sales_manager]
        self.finance = [u for u in self.users.values() if u.role == Role.finance]
        styles = [(4, 2), (6, 3), (9, 4), (5, 2), (7, 3), (3, 2), (8, 3), (5, 3)]
        for rep, style in zip(self.reps, styles):
            self.rep_style[rep.id] = style
        self.stats["users"] = len(self.users)

    # ------------------------------------------------------------------ 2. catalog

    def seed_catalog(self):
        for i, (name, pct, desc) in enumerate(D.TIERS):
            tier = CustomerTier(name=name, max_discount_pct=pct, description=desc, sort_order=i)
            self.db.add(tier)
            self.tiers[name] = tier
        for name, pct, tax, kind in D.CATEGORIES:
            cat = Category(name=name, max_discount_pct=pct, description=f"{name} ({'recurring' if kind == 'sub' else 'one-time'})")
            self.db.add(cat)
            self.categories[name] = cat
        self.db.flush()
        for cat_name, items in D.PRODUCTS.items():
            _, _, tax, kind = next(c for c in D.CATEGORIES if c[0] == cat_name)
            for item in items:
                name, sku, cost, price = item[:4]
                unit = item[4] if len(item) > 4 else "unit"
                product = Product(
                    sku=sku, name=name, category_id=self.categories[cat_name].id, cost=Decimal(cost), price=Decimal(price), unit=unit,
                    tax_rate_pct=Decimal(tax), product_type=ProductType.recurring if kind == "sub" else ProductType.one_time,
                    is_stocked=kind == "hw" and cat_name != "Software Licenses",
                    description=f"{name} — {cat_name.lower()}",
                )
                self.db.add(product)
                self.products[sku] = product
        self.db.flush()
        for sku, variants in D.VARIANTS.items():
            base = self.products[sku]
            for i, (vname, attrs, delta) in enumerate(variants):
                self.db.add(ProductVariant(product_id=base.id, sku=f"{sku}-V{i + 1}", name=vname, attributes=attrs, price=base.price + delta if delta else None, cost=base.cost + int(delta * 0.7) if delta else None))
        # subscription plans for recurring products
        for sku, product in self.products.items():
            if product.product_type != ProductType.recurring:
                continue
            plans = []
            for interval, factor in (("monthly", 1), ("quarterly", Decimal("2.85")), ("yearly", Decimal("10.8"))):
                plan = SubscriptionPlan(name=f"{product.name} — {interval}", product_id=product.id, interval=interval, price_per_interval=(product.price * factor).quantize(Decimal("0.01")), proration_enabled=interval != "yearly")
                self.db.add(plan)
                plans.append(plan)
            self.plans[sku] = plans
        # archived product (referenced later by history is fine)
        legacy = Product(sku="LT-OLD-2019", name="Legacy 2019 Laptop (discontinued)", category_id=self.categories["Laptops & Workstations"].id, cost=400, price=650, tax_rate_pct=8, is_active=False, is_archived=True)
        self.db.add(legacy)
        self.db.flush()
        self.stats["products"] = len(self.products) + 1
        self.stats["variants"] = sum(len(v) for v in D.VARIANTS.values())
        self.stats["subscription_plans"] = sum(len(p) for p in self.plans.values())

    def seed_pricing_rules(self):
        platinum = PriceList(name="Platinum framework agreement 2026", currency="USD", tier_id=self.tiers["Platinum"].id, valid_from=TODAY - timedelta(days=200), valid_to=TODAY + timedelta(days=165), priority=10)
        volume = PriceList(name="Volume price breaks", currency="USD", priority=1)
        self.db.add_all([platinum, volume])
        self.db.flush()
        hardware = [p for p in self.products.values() if p.category.name in ("Laptops & Workstations", "Servers & Storage", "Networking")]
        for product in self.pick(hardware, 24):
            self.db.add(PriceListItem(price_list_id=platinum.id, product_id=product.id, unit_price=(product.price * Decimal("0.95")).quantize(Decimal("0.01"))))
        for product in self.pick([p for p in self.products.values() if p.category.name in ("Peripherals & Accessories", "Networking", "Software Licenses")], 18):
            self.db.add(PriceListItem(price_list_id=volume.id, product_id=product.id, min_quantity=10, unit_price=(product.price * Decimal("0.93")).quantize(Decimal("0.01"))))
            self.db.add(PriceListItem(price_list_id=volume.id, product_id=product.id, min_quantity=50, unit_price=(product.price * Decimal("0.88")).quantize(Decimal("0.01"))))
        rules = [
            DiscountRule(name="Gold accounts on Software Licenses", scope="tier_category", tier_id=self.tiers["Gold"].id, category_id=self.categories["Software Licenses"].id, max_discount_pct=20),
            DiscountRule(name="Platinum accounts on Professional Services", scope="tier_category", tier_id=self.tiers["Platinum"].id, category_id=self.categories["Professional Services"].id, max_discount_pct=15),
            DiscountRule(name="Bronze accounts on Servers & Storage", scope="tier_category", tier_id=self.tiers["Bronze"].id, category_id=self.categories["Servers & Storage"].id, max_discount_pct=3),
            DiscountRule(name="Q3 clearance: Nimbus 13 Convertible", scope="product", product_id=self.products["LT-NMB13"].id, max_discount_pct=30, valid_from=TODAY - timedelta(days=60), valid_to=TODAY + timedelta(days=30)),
            DiscountRule(name="Expired promo: Horizon 27\" monitor", scope="product", product_id=self.products["PR-HZN-27Q"].id, max_discount_pct=35, valid_from=TODAY - timedelta(days=200), valid_to=TODAY - timedelta(days=100)),
            DiscountRule(name="Inactive: Peripherals blanket 25%", scope="category", category_id=self.categories["Peripherals & Accessories"].id, max_discount_pct=25, is_active=False),
        ]
        self.db.add_all(rules)
        self.db.add_all([
            ApprovalRule(name="Sales Manager approval above 5 points", approval_level="manager", min_points_over=5, expires_after_days=14),
            ApprovalRule(name="Finance approval above 15 points", approval_level="manager_then_finance", min_points_over=15, min_excess_amount=25000, expires_after_days=14),
        ])
        self.db.flush()
        self.stats["price_list_items"] = 24 + 36
        self.stats["discount_rules"] = len(rules)

    # ------------------------------------------------------------------ 3. warehouses + stock

    def seed_inventory(self):
        for code, name, weight, city, country in D.WAREHOUSES:
            wh = Warehouse(code=code, name=name, shipping_cost_weight=Decimal(str(weight)), city=city, country=country)
            self.db.add(wh)
            self.warehouses.append(wh)
        self.db.flush()
        physical = [p for p in self.products.values() if p.product_type == ProductType.one_time and p.is_stocked]
        count = 0
        for product in physical:
            for wh in self.pick(self.warehouses, self.rng.randint(2, 4)):
                if product.sku in ("ST-VLT-SAN24", "SV-KST-R740", "NW-SNT-1200"):
                    qty = self.rng.choice([0, 1, 2, 3])
                elif product.price > 2000:
                    qty = self.rng.randint(4, 30)
                elif product.price > 300:
                    qty = self.rng.randint(25, 160)
                else:
                    qty = self.rng.randint(80, 900)
                stock = inventory_service.get_stock(self.db, wh.id, product.id, create=True)
                stock.reorder_point = max(2, qty // 8)
                if qty:
                    inventory_service.receive(self.db, wh.id, product.id, qty, self.admin, "Opening balance", reference_type="opening_balance")
                count += 1
        # a deliberately empty SKU everywhere: zero stock edge case
        empty = self.products["NW-WLC-500"]
        for stock in self.db.query(type(inventory_service.get_stock(self.db, self.warehouses[0].id, empty.id, create=True))).filter_by(product_id=empty.id).all():
            stock.quantity_on_hand = 0
        self.db.flush()
        self.stats["warehouses"] = len(self.warehouses)
        self.stats["stock_rows"] = count

    # ------------------------------------------------------------------ 4. customers

    def seed_customers(self):
        tiers = ["Platinum"] * 12 + ["Gold"] * 28 + ["Silver"] * 28 + ["Bronze"] * 14
        self.rng.shuffle(tiers)
        for i, (name, industry, domain, city, state, country) in enumerate(D.CUSTOMERS):
            first, last = self.one(D.FIRST_NAMES), self.one(D.LAST_NAMES)
            owner = self.reps[i % len(self.reps)]
            customer = Customer(
                code=next_number(self.db, "customer"), name=name, tier_id=self.tiers[tiers[i % len(tiers)]].id, owner_user_id=owner.id, industry=industry,
                email=f"procurement@{domain}", phone=f"+1 {self.rng.randint(200, 989)}-{self.rng.randint(200, 999)}-{self.rng.randint(1000, 9999)}", website=f"https://www.{domain}",
                contact_name=f"{first} {last}", billing_address_line1=f"{self.rng.randint(10, 9800)} {self.one(['Main', 'Market', 'Commerce', 'Industrial', 'Harbor', 'Lakeshore', 'Innovation'])} {self.one(['St', 'Ave', 'Blvd', 'Way', 'Pkwy'])}",
                billing_city=city, billing_state=state, billing_postal_code=f"{self.rng.randint(10000, 99999)}", billing_country=country,
                shipping_address_line1=f"{self.rng.randint(10, 9800)} {self.one(['Depot', 'Warehouse', 'Logistics', 'Distribution'])} Rd", shipping_city=city, shipping_state=state,
                shipping_postal_code=f"{self.rng.randint(10000, 99999)}", shipping_country=country, payment_terms_days=self.one([14, 30, 30, 30, 45, 60]), currency="USD",
                is_active=i not in (77, 78),
            )
            self.db.add(customer)
            self.customers.append(customer)
        self.db.flush()
        hashed = hash_password(D.DEMO_PASSWORD)
        by_name = {c.name: c for c in self.customers}
        for email, name, customer_name in D.CUSTOMER_USERS:
            self.db.add(User(email=email, full_name=name, hashed_password=hashed, role=Role.customer, customer_id=by_name[customer_name].id))
        self.db.flush()
        self.stats["customers"] = len(self.customers)

    # ------------------------------------------------------------------ 5. pairings

    def seed_pairings(self):
        P = self.products
        pairs = []
        laptops = [s for s in P if s.startswith(("LT-", "WS-", "TB-"))]
        for sku in laptops:
            pairs += [(sku, "AC-DOCK-TR3", 62), (sku, "PR-HZN-27Q", 48), (sku, "SP-BUS", 35), (sku, "SW-EPS-DEV", 55), (sku, "PR-BAG-PRO", 30)]
        for sku in [s for s in P if s.startswith("SV-KST")]:
            pairs += [(sku, "ST-SSD-3840", 70), (sku, "SV-MEM-128", 58), (sku, "SV-UPS-3K", 44), (sku, "SP-MC", 52), (sku, "PS-INST-DAY", 40), (sku, "SW-VRT-STD", 36)]
        for sku in [s for s in P if s.startswith("NW-MRD")]:
            pairs += [(sku, "NW-SFP-10G", 75), (sku, "NW-BCN-AX", 50), (sku, "NW-PP-48", 45), (sku, "SP-NET-MON", 38), (sku, "PS-NET-WS", 25)]
        pairs += [("NW-SNT-200", "SP-BUS", 40), ("NW-SNT-600", "PS-FW-CFG", 60), ("NW-SNT-1200", "PS-FW-CFG", 65), ("ST-VLT-NAS8", "ST-HDD-16T", 80), ("ST-VLT-NAS16", "ST-HDD-16T", 82), ("PR-HZN-27Q", "PR-ARM-2", 52), ("PR-HZN-32K", "PR-ARM-2", 55), ("SW-OFF-USR", "CL-M365-USR", 45), ("PS-SEC-ASM", "CL-SIEM-100", 33), ("SV-RACK-42U", "SV-PDU-30A", 77)]
        promoted = {("LT-ATL14-BAS", "SP-BUS"), ("SV-KST-R440", "SP-MC"), ("NW-MRD-48P", "SP-NET-MON"), ("LT-SMT-X1", "AC-DOCK-TR3")}
        seen = set()
        for base, sug, score in pairs:
            if (base, sug) in seen or base == sug:
                continue
            seen.add((base, sug))
            promo = (base, sug) in promoted
            self.db.add(ProductPairing(base_product_id=P[base].id, suggested_product_id=P[sug].id, co_purchase_score=score, is_promoted=promo, promotion_label="Attach-rate promotion: bundle discount eligible" if promo else None, promotion_start=TODAY - timedelta(days=30) if promo else None, promotion_end=TODAY + timedelta(days=60) if promo else None))
        self.db.flush()
        self.stats["product_pairings"] = len(seen)

    # ------------------------------------------------------------------ 6. quotes

    def _lines_for(self, customer: Customer, rep: User, *, n: Optional[int] = None, over_limit: Optional[str] = None, include_recurring: bool = False, products: Optional[List[str]] = None) -> List[QuoteLineCreate]:
        mean, spread = self.rep_style[rep.id]
        n = n or self.rng.choice([1, 2, 2, 3, 3, 4, 5])
        scarce = {"ST-VLT-SAN24", "SV-KST-R740", "NW-SNT-1200", "NW-WLC-500"}
        one_time = [p for p in self.products.values() if p.product_type == ProductType.one_time and p.sku not in scarce]
        weights = [3 if p.category.name in ("Laptops & Workstations", "Networking", "Peripherals & Accessories") else 1 for p in one_time]
        chosen = [self.products[s] for s in products] if products else self.rng.choices(one_time, weights=weights, k=n)
        seen = set()
        specs = []
        for product in chosen:
            if product.id in seen:
                continue
            seen.add(product.id)
            limit, _ = __import__("app.services.discount_service", fromlist=["x"]).allowed_discount_for(self.db, product, customer)
            qty = self.rng.choice([1, 1, 2, 3, 5, 8, 10, 12, 20, 25]) if product.price < 1500 else self.rng.choice([1, 1, 2, 2, 3])
            disc = max(0, min(float(limit), self.rng.gauss(mean, spread)))
            disc = round(disc * 2) / 2
            specs.append(QuoteLineCreate(product_id=product.id, quantity=qty, discount_pct=Decimal(str(disc))))
        if over_limit and specs:
            target = specs[0]
            product = self.db.get(Product, target.product_id)
            limit, _ = __import__("app.services.discount_service", fromlist=["x"]).allowed_discount_for(self.db, product, customer)
            extra = {"at_threshold": 5, "one_over": 6, "manager": self.rng.choice([6, 8, 10, 12]), "finance": self.rng.choice([16, 20, 25]), "within": 0}[over_limit]
            target.discount_pct = Decimal(str(float(limit) + extra))
        if include_recurring:
            sku = self.one(list(self.plans))
            plan = self.one(self.plans[sku][:2])
            specs.append(QuoteLineCreate(product_id=self.products[sku].id, quantity=self.rng.choice([5, 10, 25, 50]), discount_pct=Decimal("0"), subscription_plan_id=plan.id))
        return specs

    def _new_quote(self, customer: Customer, rep: User, *, promised_days: Optional[int] = None, **kw) -> Quote:
        lines = self._lines_for(customer, rep, **kw)
        quote = quote_service.create_quote(
            self.db, rep, customer_id=customer.id, lines=lines, valid_until=TODAY + timedelta(days=self.rng.randint(15, 45)),
            promised_delivery_date=TODAY + timedelta(days=promised_days) if promised_days is not None else None,
            notes=self.one([None, None, "Net terms per MSA.", "Customer prefers a single delivery.", "Renewal of last year's order."]),
        )
        self.db.flush()
        return self.quote(quote.id)

    def _manager_for(self, rep: User) -> User:
        return next((m for m in self.managers if m.team == rep.team), self.managers[0])

    def _approve_chain(self, quote: Quote, rep: User, note: Optional[str] = None) -> Quote:
        """Approve whatever is pending (manager, then finance if required)."""
        quote = self.quote(quote.id)
        if quote.status != QuoteStatus.pending_approval:
            return quote
        approval_service.act(self.db, quote, self._manager_for(rep), "approved", note or self.one(["Strategic account, approved.", "Within quarter targets.", "OK given volume commitment.", None]))
        quote = self.quote(quote.id)
        if quote.status == QuoteStatus.pending_approval and quote.current_approval_step == "finance":
            approval_service.act(self.db, quote, self.one(self.finance), "approved", self.one(["Margin acceptable after review.", "Approved — cash terms confirmed.", None]))
        return self.quote(quote.id)

    def _negotiate(self, quote: Quote, rep: User, *, escalate: bool, approve: Optional[bool] = True) -> Quote:
        quote = self.quote(quote.id)
        line = self.one(quote.lines)
        portal_service.add_customer_comment(self.db, quote, line.id, self.one(D.CUSTOMER_QUESTIONS))
        if self.rng.random() < 0.7:
            portal_service.add_rep_comment(self.db, quote, rep, line.id, self.one(D.REP_REPLIES), False)
        target = self.one([l for l in quote.lines if not l.is_recurring] or quote.lines)
        bump = self.rng.choice([8, 10, 12]) if escalate else self.rng.choice([0.5, 1, 1.5, 2])
        proposal, risk = portal_service.submit_counter_proposal(self.db, self.quote(quote.id), [{"quote_line_id": target.id, "proposed_discount_pct": float(target.discount_pct) + bump}], self.one(["Can you do a little better on this line?", "Our budget is tight this quarter.", "Competitor quoted lower — can you match?"]))
        quote = self.quote(quote.id)
        if quote.status == QuoteStatus.pending_approval and approve is not None:
            actor = self._manager_for(rep)
            approval_service.act(self.db, quote, actor, "approved" if approve else "rejected", "Approved the counter-offer to close the deal." if approve else "Cannot go that deep on this SKU.")
            quote = self.quote(quote.id)
            if quote.status == QuoteStatus.pending_approval and quote.current_approval_step == "finance":
                approval_service.act(self.db, quote, self.one(self.finance), "approved", None)
        return self.quote(quote.id)

    def _fulfil(self, quote: Quote, rep: User, stage: str, *, late: bool = False) -> Quote:
        """stage: planned | reserved | partial | shipped | delivered"""
        ops = self.one(self.finance)
        quote = self.quote(quote.id)
        if not any(fulfillment_service.needs_shipping(l) for l in quote.lines):
            return quote
        self.db.commit()  # the order itself is safe even if fulfilment below is skipped
        fulfillment_service.suggest(self.db, quote, ops)
        if stage == "planned":
            return self.quote(quote.id)
        try:
            fulfillment_service.confirm(self.db, self.quote(quote.id), ops)
        except StockShortage:
            self.db.rollback()
            fulfillment_service.suggest(self.db, self.quote(quote.id), ops)  # re-plan against current stock
            fulfillment_service.confirm(self.db, self.quote(quote.id), ops)
        if stage == "reserved":
            return self.quote(quote.id)
        try:
            shipments = fulfillment_service.ship(self.db, self.quote(quote.id), ops, expected_date=TODAY + timedelta(days=self.rng.randint(2, 9)) if not late else quote.promised_delivery_date + timedelta(days=self.rng.randint(3, 12)) if quote.promised_delivery_date else None)
        except StateTransitionError:
            return self.quote(quote.id)  # everything on this order is backordered
        if stage in ("shipped", "partial"):
            return self.quote(quote.id)
        for sh in shipments:
            delivered_at = NOW if not late else NOW
            fulfillment_service.deliver(self.db, self.quote(quote.id), sh.id, ops, delivered_at)
        return self.quote(quote.id)

    def _invoice_and_pay(self, quote: Quote, how: str) -> Optional[Invoice]:
        """how: none | unpaid | partial | paid | overdue | void | duplicate"""
        if how == "none":
            return None
        ops = self.one(self.finance)
        try:
            invoice = invoice_service.generate_invoice_for_confirmed_fulfillment(quote.id, self.db, actor=ops, commit=False)
        except Exception:
            return None
        if how == "duplicate":
            try:
                invoice_service.generate_invoice_for_confirmed_fulfillment(quote.id, self.db, actor=ops, commit=False)
            except Exception:
                pass  # correctly refused: everything shipped is already invoiced
            how = "unpaid"
        amount = Decimal(invoice.amount)
        if how == "paid":
            invoice_service.record_payment(invoice.id, amount, self.one(["Bank Transfer", "ACH", "Card", "Cheque"]), ops, self.db, reference=f"REF-{self.rng.randint(100000, 999999)}", idempotency_key=f"seed-pay-{invoice.id}", commit=False)
            # a duplicate submission with the same key must be a no-op
            invoice_service.record_payment(invoice.id, amount, "Bank Transfer", ops, self.db, idempotency_key=f"seed-pay-{invoice.id}", commit=False)
        elif how == "partial":
            invoice_service.record_payment(invoice.id, (amount * Decimal("0.4")).quantize(Decimal("0.01")), "Bank Transfer", ops, self.db, reference=f"REF-{self.rng.randint(100000, 999999)}", commit=False)
        elif how == "void":
            invoice_service.void_invoice(invoice.id, ops, "Issued against the wrong purchase order", self.db)
            invoice_service.generate_invoice_for_confirmed_fulfillment(quote.id, self.db, actor=ops, commit=False)
        self.db.flush()
        return invoice

    def _backdate(self, quote: Quote, age_days: int, *, stalled: bool = False, span_days: Optional[int] = None):
        """Shift the whole timeline of a quote into the past."""
        created = NOW - timedelta(days=age_days, hours=self.rng.randint(0, 20))
        span = timedelta(days=span_days if span_days is not None else min(age_days, self.rng.randint(1, 14)))
        last = created + timedelta(days=1) if stalled else created + span
        q = self.db.get(Quote, quote.id)
        q.created_at = created
        q.updated_at = last
        q.last_activity_at = min(last, NOW)
        if q.sent_at:
            q.sent_at = created + span * 0.4
        if q.confirmed_at:
            q.confirmed_at = created + span * 0.6
        logs = self.db.query(AuditLog).filter(AuditLog.quote_id == q.id).order_by(AuditLog.id).all()
        for i, log in enumerate(logs):
            log.timestamp = created + (span * i / max(1, len(logs) - 1) if not stalled else timedelta(hours=i))
        for req in self.db.query(ApprovalRequest).filter(ApprovalRequest.quote_id == q.id).all():
            req.created_at = created + span * 0.3
            if req.expires_at:
                req.expires_at = req.created_at + timedelta(days=14)
            if req.resolved_at:
                req.resolved_at = created + span * 0.5
        for act in self.db.query(ApprovalAction).filter(ApprovalAction.quote_id == q.id).all():
            act.timestamp = created + span * 0.5
        for cp in self.db.query(CounterProposal).filter(CounterProposal.quote_id == q.id).all():
            cp.created_at = created + span * 0.45
        for c in self.db.query(LineComment).filter(LineComment.quote_line_id.in_([l.id for l in q.lines])).all():
            c.created_at = created + span * 0.42
        for n in self.db.query(Notification).filter(Notification.entity_type == "quote", Notification.entity_id == q.id).all():
            n.created_at = created + span * 0.5
        for e in self.db.query(EmailMessage).filter(EmailMessage.entity_type == "quote", EmailMessage.entity_id == q.id).all():
            e.created_at = created + span * 0.4
        for plan in self.db.query(FulfillmentPlan).filter(FulfillmentPlan.quote_id == q.id).all():
            plan.created_at = created + span * 0.7
        for sh in self.db.query(Shipment).filter(Shipment.quote_id == q.id).all():
            sh.created_at = created + span * 0.75
            sh.shipped_at = sh.created_at
            if sh.delivered_at:
                if sh.promised_date and sh.expected_date and sh.expected_date > sh.promised_date:
                    sh.delivered_at = datetime.combine(sh.expected_date, datetime.min.time(), tzinfo=timezone.utc)
                else:
                    sh.delivered_at = min(NOW, sh.shipped_at + timedelta(days=self.rng.randint(1, 5)))
                q.actual_delivery_date = sh.delivered_at.date()
        for inv in self.db.query(Invoice).filter(Invoice.quote_id == q.id).all():
            inv.issued_at = created + span * 0.8
            inv.due_date = (inv.issued_at + timedelta(days=q.customer.payment_terms_days)).date()
            if inv.paid_at:
                inv.paid_at = min(NOW, inv.issued_at + timedelta(days=self.rng.randint(1, 20)))
            for p in inv.payments:
                p.paid_at = inv.paid_at or (inv.issued_at + timedelta(days=self.rng.randint(1, 15)))
        self.db.flush()

    def seed_quotes(self):
        active_customers = [c for c in self.customers if c.is_active]

        def cust_rep():
            c = self.one(active_customers)
            return c, self.db.get(User, c.owner_user_id)

        counts = {}

        def tally(k):
            counts[k] = counts.get(k, 0) + 1
            self.db.commit()

        # -- drafts (30): some fresh, some stalled
        for i in range(30):
            c, rep = cust_rep()
            q = self._new_quote(c, rep, include_recurring=self.rng.random() < 0.2)
            stalled = i < 9
            self._backdate(q, self.rng.randint(9, 35) if stalled else self.rng.randint(0, 6), stalled=stalled)
            tally("draft")

        # -- pending approval (14): manager step, finance step, aging ones
        for i in range(14):
            c, rep = cust_rep()
            q = self._new_quote(c, rep, over_limit="finance" if i % 3 == 0 else "manager")
            approval_service.submit(self.db, q, rep)
            q = self.quote(q.id)
            if i % 3 == 0:
                approval_service.act(self.db, q, self._manager_for(rep), "approved", "Escalating to finance per policy.")
            self._backdate(q, self.rng.randint(0, 9) if i < 10 else self.rng.randint(4, 8), span_days=1)
            tally("pending_approval")

        # -- edge cases around thresholds
        c, rep = cust_rep()
        for kind in ("at_threshold", "one_over", "within"):
            q = self._new_quote(c, rep, n=1, over_limit=kind)
            approval_service.submit(self.db, q, rep)
            self._backdate(self.quote(q.id), self.rng.randint(1, 5), span_days=1)
            tally("pending_approval" if kind != "within" else "approved")
        # multiple small violations -> blended risk
        specs = self._lines_for(c, rep, n=3)
        for s in specs:
            product = self.db.get(Product, s.product_id)
            limit, _ = __import__("app.services.discount_service", fromlist=["x"]).allowed_discount_for(self.db, product, c)
            s.discount_pct = Decimal(str(float(limit) + 2))
        q = quote_service.create_quote(self.db, rep, customer_id=c.id, lines=specs, notes="Several lines slightly over policy — blended risk example.")
        approval_service.submit(self.db, self.quote(q.id), rep)
        self._backdate(self.quote(q.id), 2, span_days=1)
        tally("pending_approval")

        # -- approved, not yet sent (18)
        for i in range(18):
            c, rep = cust_rep()
            q = self._new_quote(c, rep, over_limit="manager" if i % 4 == 0 else None)
            approval_service.submit(self.db, q, rep)
            q = self._approve_chain(q, rep)
            self._backdate(q, self.rng.randint(1, 20), stalled=i < 3)
            tally("approved")

        # -- sent, waiting for customer (20)
        for i in range(20):
            c, rep = cust_rep()
            q = self._new_quote(c, rep, include_recurring=i % 5 == 0)
            approval_service.submit(self.db, q, rep)
            q = self._approve_chain(q, rep)
            portal_service.send_to_customer(self.db, q, rep)
            self._backdate(self.quote(q.id), self.rng.randint(1, 25), stalled=i < 4)
            tally("sent")

        # -- under negotiation (14): 6 accepted within limits, 5 approved after escalation, 3 still pending approval
        for i in range(14):
            c, rep = cust_rep()
            q = self._new_quote(c, rep)
            approval_service.submit(self.db, q, rep)
            q = self._approve_chain(q, rep)
            portal_service.send_to_customer(self.db, q, rep)
            q = self._negotiate(q, rep, escalate=i >= 6, approve=(True if i < 11 else None))
            self._backdate(q, self.rng.randint(1, 12), span_days=2)
            tally(q.status.value)

        # -- revision required (6) and rejected (10)
        for i in range(6):
            c, rep = cust_rep()
            q = self._new_quote(c, rep, over_limit="manager")
            approval_service.submit(self.db, q, rep)
            approval_service.act(self.db, self.quote(q.id), self._manager_for(rep), "returned_for_revision", self.one(["Trim the discount on the first line.", "Please add the support plan before I approve.", "Quantities look off — double-check with the customer."]))
            self._backdate(self.quote(q.id), self.rng.randint(1, 12), stalled=i < 2)
            tally("revision_required")
        for i in range(10):
            c, rep = cust_rep()
            q = self._new_quote(c, rep, over_limit="finance" if i % 2 else "manager")
            approval_service.submit(self.db, q, rep)
            q = self.quote(q.id)
            if i % 2:
                approval_service.act(self.db, q, self._manager_for(rep), "approved", None)
                approval_service.act(self.db, self.quote(q.id), self.one(self.finance), "rejected", "Below margin floor for this category.")
            else:
                approval_service.act(self.db, q, self._manager_for(rep), "rejected", self.one(["Discount too deep for a Bronze account.", "We can't discount services this far.", "Customer has outstanding invoices — no further discount."]))
            self._backdate(self.quote(q.id), self.rng.randint(5, 120), span_days=3)
            tally("rejected")

        # -- quote modified after approval -> new version pending again (4)
        for i in range(4):
            c, rep = cust_rep()
            q = self._new_quote(c, rep)
            approval_service.submit(self.db, q, rep)
            q = self._approve_chain(q, rep)
            quote_service.revise(self.db, q, rep, "Customer asked for a bigger discount after approval")
            q = self.quote(q.id)
            line = q.lines[0]
            quote_service.update_line(self.db, q, rep, line.id, {"discount_pct": float(line.discount_pct) + 9})
            approval_service.submit(self.db, self.quote(q.id), rep)
            self._backdate(self.quote(q.id), self.rng.randint(1, 6), span_days=2)
            tally("pending_approval (revised)")

        # -- cancelled (6) and expired (8)
        for i in range(6):
            c, rep = cust_rep()
            q = self._new_quote(c, rep)
            quote_service.cancel(self.db, q, rep, self.one(["Customer chose another vendor.", "Project postponed to next fiscal year.", "Duplicate of another quotation."]))
            self._backdate(self.quote(q.id), self.rng.randint(10, 150), span_days=4)
            tally("cancelled")
        for i in range(8):
            c, rep = cust_rep()
            q = self._new_quote(c, rep)
            approval_service.submit(self.db, q, rep)
            q = self._approve_chain(q, rep)
            if i % 2:
                portal_service.send_to_customer(self.db, q, rep)
            self.db.get(Quote, q.id).valid_until = TODAY - timedelta(days=self.rng.randint(1, 40))
            self.db.flush()
            self._backdate(self.quote(q.id), self.rng.randint(40, 140), span_days=5)
        quote_service.expire_stale_quotes(self.db)
        counts["expired"] = 8

        # -- confirmed orders (120): fulfillment + billing + subscriptions across stages
        stages = ["delivered"] * 55 + ["shipped"] * 22 + ["partial"] * 10 + ["reserved"] * 12 + ["planned"] * 9 + ["none"] * 12
        self.rng.shuffle(stages)
        billing_modes = ["paid"] * 48 + ["partial"] * 12 + ["unpaid"] * 12 + ["overdue"] * 10 + ["void"] * 2 + ["duplicate"] * 3
        self.rng.shuffle(billing_modes)
        products_all = list(self.products.values())
        for i, stage in enumerate(stages):
            c, rep = cust_rep()
            hybrid = i % 4 == 0
            promised = self.rng.randint(5, 30)
            late = stage in ("delivered", "shipped", "partial", "reserved") and i % 9 == 0
            kwargs = {"include_recurring": hybrid, "over_limit": "manager" if i % 6 == 0 else ("finance" if i % 17 == 0 else None)}
            if stage == "partial":
                # order more than total stock of a scarce product -> backorder
                scarce = self.one(["ST-VLT-SAN24", "SV-KST-R740", "NW-SNT-1200", "NW-WLC-500"])
                kwargs["products"] = [scarce, self.one([p.sku for p in products_all if p.product_type == ProductType.one_time and p.price < 500])]
                kwargs["n"] = 2
            q = self._new_quote(c, rep, promised_days=promised if not late else -self.rng.randint(1, 10), **kwargs)
            if stage == "partial":
                line = q.lines[0]
                quote_service.update_line(self.db, q, rep, line.id, {"quantity": 8})
                q = self.quote(q.id)
            approval_service.submit(self.db, q, rep)
            q = self._approve_chain(q, rep)
            if i % 5 == 0:
                portal_service.send_to_customer(self.db, q, rep)
                if i % 10 == 0:
                    q = self._negotiate(q, rep, escalate=i % 20 == 0, approve=True)
                portal_service.confirm(self.db, self.quote(q.id))
            else:
                if q.status == QuoteStatus.approved:
                    quote_service.transition(q, QuoteStatus.sent)
                    q.sent_at = NOW
                portal_service.confirm(self.db, self.quote(q.id), via="internal confirmation (signed PO)")
            q = self.quote(q.id)
            mode = billing_modes[i % len(billing_modes)] if stage in ("delivered", "shipped", "partial") else "none"
            # unpaid/partial invoices are recent (still within terms); overdue ones are explicitly back-dated below
            age = self.rng.randint(3, 240) if stage in ("delivered", "shipped") and mode in ("paid", "void", "duplicate", "none") else self.rng.randint(1, 12)
            if stage != "none":
                q = self._fulfil(q, rep, stage, late=late)
            invoice = None
            if mode != "none":
                invoice = self._invoice_and_pay(q, mode)
            self._backdate(self.quote(q.id), age, span_days=min(age, self.rng.randint(2, 12)))
            if invoice is not None and mode == "overdue":
                inv = self.db.get(Invoice, invoice.id)
                inv.due_date = TODAY - timedelta(days=self.rng.randint(3, 45))
                inv.issued_at = datetime.combine(inv.due_date - timedelta(days=30), datetime.min.time(), tzinfo=timezone.utc)
            tally("confirmed")
        self.db.flush()
        invoice_service.refresh_overdue(self.db)
        self.stats.update({f"quotes_{k}": v for k, v in counts.items()})

    # ------------------------------------------------------------------ 7. subscriptions lifecycle

    def seed_subscription_lifecycle(self):
        subs = self.db.query(Subscription).order_by(Subscription.id).all()
        ops = self.one(self.finance)
        for i, sub in enumerate(subs):
            sub = subscription_service.load(self.db, sub.id)
            months_ago = self.rng.randint(0, 7)
            start = (TODAY - timedelta(days=30 * months_ago)).replace(day=min(TODAY.day, 28))
            from app.services.billing_engine import next_cycle_dates

            cs, ce = next_cycle_dates(start, sub.plan.interval.value)
            sub.start_date, sub.current_cycle_start, sub.current_cycle_end, sub.next_billing_date = start, cs, ce, ce
            for ev in sub.billing_events:
                ev.event_date = start
            self.db.flush()
            renewals = 0
            while sub.next_billing_date and sub.next_billing_date <= TODAY and renewals < 8:
                event, invoice = subscription_service.advance_cycle(self.db, sub, ops)
                renewals += 1
                if invoice is not None:
                    invoice.issued_at = datetime.combine(event.event_date, datetime.min.time(), tzinfo=timezone.utc)
                    invoice.due_date = event.event_date + timedelta(days=sub.customer.payment_terms_days if sub.customer else 30)
                    if invoice.due_date < TODAY - timedelta(days=3) and i % 5 != 0:
                        invoice_service.record_payment(invoice.id, Decimal(invoice.amount), "ACH", ops, self.db, reference=f"SUB-{sub.id}-{renewals}", commit=False)
                        invoice.paid_at = datetime.combine(min(TODAY, invoice.due_date - timedelta(days=2)), datetime.min.time(), tzinfo=timezone.utc)
                        for p in invoice.payments:
                            p.paid_at = invoice.paid_at
                self.db.flush()
            if i % 6 == 1 and sub.status.value == "active":
                mid = sub.current_cycle_start + timedelta(days=max(1, (sub.current_cycle_end - sub.current_cycle_start).days // 2))
                subscription_service.change_quantity(self.db, sub, sub.quantity + self.rng.choice([-2, 3, 5]) if sub.quantity > 2 else sub.quantity + 3, min(mid, TODAY), ops)
            elif i % 11 == 2 and sub.status.value == "active":
                subscription_service.cancel(self.db, sub, min(TODAY, sub.current_cycle_start + timedelta(days=10)), ops, "Customer consolidated vendors")
            elif i % 13 == 4 and sub.status.value == "active":
                subscription_service.pause(self.db, sub, ops)
            self.db.flush()
        invoice_service.refresh_overdue(self.db)
        self.stats["subscriptions"] = len(subs)

    # ------------------------------------------------------------------ 8. deal health + housekeeping

    def seed_deal_health(self):
        result = deal_health_service.run(self.db)
        alerts = self.db.query(DealHealthAlert).order_by(DealHealthAlert.id).all()
        manager = self.managers[0]
        for alert in alerts[:3]:
            alert = deal_health_service.load_alert(self.db, alert.id)
            try:
                deal_health_service.act(self.db, alert, manager, "notify_rep", "Please follow up with the customer this week.")
            except Exception:
                self.db.rollback()
        for alert in alerts[3:5]:
            alert = deal_health_service.load_alert(self.db, alert.id)
            deal_health_service.act(self.db, alert, manager, "acknowledge", "Known — customer is in budget freeze.")
        self.db.flush()
        self.stats["deal_health_alerts"] = result["open"]

    # ------------------------------------------------------------------ run

    def run(self):
        for step in (self.seed_users, self.seed_catalog, self.seed_pricing_rules, self.seed_inventory, self.seed_customers, self.seed_pairings, self.seed_quotes, self.seed_subscription_lifecycle, self.seed_deal_health):
            logger.info("seed step", extra={"extra_fields": {"step": step.__name__}})
            step()
            self.db.commit()
        self.stats["audit_logs"] = self.db.query(AuditLog).count()
        self.stats["invoices"] = self.db.query(Invoice).count()
        self.stats["payments"] = self.db.query(Payment).count()
        self.stats["notifications"] = self.db.query(Notification).count()
        self.stats["emails"] = self.db.query(EmailMessage).count()
        self.stats["quotes_total"] = self.db.query(Quote).count()
        self.stats["quote_lines"] = self.db.query(QuoteLine).count()
        return self.stats


def wipe(db: Session) -> None:
    """Delete every row in dependency order. Never drops tables."""
    # users <-> customers reference each other; break the cycle first.
    db.execute(text("UPDATE customers SET owner_user_id = NULL"))
    db.execute(text("UPDATE users SET customer_id = NULL"))
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()


def database_is_empty(db: Session) -> bool:
    return db.query(User).count() == 0


def run_seed(*, fresh: bool = False, force: bool = False, seed: int = 42) -> dict:
    if fresh and settings.is_production and not force:
        raise SystemExit("Refusing to wipe a production database. Pass --force if you really mean it.")
    for name in ("dealflow.email", "dealflow.notifications", "dealflow.request"):
        logging.getLogger(name).setLevel(logging.WARNING)
    with SessionLocal() as db:
        if fresh:
            wipe(db)
        elif not database_is_empty(db):
            return {"skipped": "database already contains users; use --fresh to reseed"}
        seeder = Seeder(db, seed)
        stats = seeder.run()
        db.commit()
        return stats
