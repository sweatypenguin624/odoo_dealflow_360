"""Roles and the single authoritative permission map.

The backend derives every permission from the authenticated user's role.
Nothing about roles is ever trusted from the client.
"""

import enum
from typing import Dict, FrozenSet


class Role(str, enum.Enum):
    admin = "admin"
    sales_manager = "sales_manager"
    sales_rep = "sales_rep"
    finance = "finance"
    customer = "customer"


INTERNAL_ROLES: FrozenSet[Role] = frozenset({Role.admin, Role.sales_manager, Role.sales_rep, Role.finance})


class Permission(str, enum.Enum):
    # quotes
    quote_read = "quote:read"
    quote_create = "quote:create"
    quote_edit = "quote:edit"
    quote_submit = "quote:submit"
    quote_send = "quote:send"
    quote_cancel = "quote:cancel"
    # approvals
    approval_read = "approval:read"
    approval_manager = "approval:manager"
    approval_finance = "approval:finance"
    approval_rules_manage = "approval_rules:manage"
    # customers / catalog / pricing
    customer_read = "customer:read"
    customer_manage = "customer:manage"
    catalog_read = "catalog:read"
    catalog_manage = "catalog:manage"
    pricing_manage = "pricing:manage"
    discount_rules_manage = "discount_rules:manage"
    # inventory / fulfillment
    inventory_read = "inventory:read"
    inventory_manage = "inventory:manage"
    fulfillment_read = "fulfillment:read"
    fulfillment_manage = "fulfillment:manage"
    # billing
    subscription_read = "subscription:read"
    subscription_manage = "subscription:manage"
    invoice_read = "invoice:read"
    invoice_manage = "invoice:manage"
    payment_manage = "payment:manage"
    # health / reporting / admin
    deal_health_read = "deal_health:read"
    deal_health_act = "deal_health:act"
    report_read = "report:read"
    audit_read = "audit:read"
    user_manage = "user:manage"
    settings_manage = "settings:manage"


_ALL = frozenset(Permission)

ROLE_PERMISSIONS: Dict[Role, FrozenSet[Permission]] = {
    Role.admin: _ALL,
    Role.sales_manager: frozenset(
        {
            Permission.quote_read,
            Permission.quote_create,
            Permission.quote_edit,
            Permission.quote_submit,
            Permission.quote_send,
            Permission.quote_cancel,
            Permission.approval_read,
            Permission.approval_manager,
            Permission.approval_rules_manage,
            Permission.customer_read,
            Permission.customer_manage,
            Permission.catalog_read,
            Permission.inventory_read,
            Permission.fulfillment_read,
            Permission.subscription_read,
            Permission.invoice_read,
            Permission.deal_health_read,
            Permission.deal_health_act,
            Permission.report_read,
            Permission.audit_read,
        }
    ),
    Role.sales_rep: frozenset(
        {
            Permission.quote_read,
            Permission.quote_create,
            Permission.quote_edit,
            Permission.quote_submit,
            Permission.quote_send,
            Permission.quote_cancel,
            Permission.approval_read,
            Permission.customer_read,
            Permission.customer_manage,
            Permission.catalog_read,
            Permission.inventory_read,
            Permission.fulfillment_read,
            Permission.subscription_read,
            Permission.invoice_read,
            Permission.deal_health_read,
        }
    ),
    Role.finance: frozenset(
        {
            Permission.quote_read,
            Permission.approval_read,
            Permission.approval_finance,
            Permission.customer_read,
            Permission.catalog_read,
            Permission.inventory_read,
            Permission.inventory_manage,
            Permission.fulfillment_read,
            Permission.fulfillment_manage,
            Permission.subscription_read,
            Permission.subscription_manage,
            Permission.invoice_read,
            Permission.invoice_manage,
            Permission.payment_manage,
            Permission.deal_health_read,
            Permission.deal_health_act,
            Permission.report_read,
            Permission.audit_read,
        }
    ),
    Role.customer: frozenset(),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def permissions_for(role: Role) -> list[str]:
    return sorted(p.value for p in ROLE_PERMISSIONS.get(role, frozenset()))
