"""catalog, customers, price lists, discount and approval rules

Revision ID: p2_catalog_pricing
Revises: p1_users_rbac
Create Date: 2026-09-05

Hand-authored production migration (generated from the model metadata,
then edited). Type widenings (Float -> Numeric, native PostgreSQL enums
-> VARCHAR) are one-way: the downgrade restores tables, columns, indexes
and constraints but keeps the widened types, which remain compatible
with the previous code.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'p2_catalog_pricing'
down_revision: Union[str, Sequence[str], None] = 'p1_users_rbac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('approval_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('approval_level', sa.Enum('manager', 'manager_then_finance', name='approvallevel_str', native_enum=False, length=32), nullable=False),
    sa.Column('min_points_over', sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column('min_excess_amount', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('valid_from', sa.Date(), nullable=True),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('expires_after_days', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('price_lists',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('tier_id', sa.Integer(), nullable=True),
    sa.Column('valid_from', sa.Date(), nullable=True),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tier_id'], ['customer_tiers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('discount_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('scope', sa.Enum('tier', 'category', 'tier_category', 'product', name='discountrulescope_str', native_enum=False, length=32), nullable=False),
    sa.Column('tier_id', sa.Integer(), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('max_discount_pct', sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=True),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.ForeignKeyConstraint(['tier_id'], ['customer_tiers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('product_variants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('sku', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('attributes', sa.JSON(), nullable=False),
    sa.Column('price', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('cost', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('price_list_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('price_list_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('variant_id', sa.Integer(), nullable=True),
    sa.Column('min_quantity', sa.Integer(), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.ForeignKeyConstraint(['price_list_id'], ['price_lists.id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('price_list_id', 'product_id', 'variant_id', 'min_quantity', name='uq_price_list_item')
    )
    op.add_column('customer_tiers', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('customer_tiers', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('customer_tiers', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('customer_tiers', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('customer_tiers', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('customer_tiers', 'max_discount_pct',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=6, scale=2),
               existing_nullable=False)
    op.create_unique_constraint('uq_customer_tiers_name', 'customer_tiers', ['name'])
    op.add_column('customers', sa.Column('code', sa.String(length=32), nullable=True))
    op.add_column('customers', sa.Column('owner_user_id', sa.Integer(), nullable=True))
    op.add_column('customers', sa.Column('industry', sa.String(length=64), nullable=True))
    op.add_column('customers', sa.Column('email', sa.String(length=255), nullable=True))
    op.add_column('customers', sa.Column('phone', sa.String(length=64), nullable=True))
    op.add_column('customers', sa.Column('website', sa.String(length=255), nullable=True))
    op.add_column('customers', sa.Column('contact_name', sa.String(length=255), nullable=True))
    op.add_column('customers', sa.Column('billing_address_line1', sa.String(length=255), nullable=True))
    op.add_column('customers', sa.Column('billing_city', sa.String(length=128), nullable=True))
    op.add_column('customers', sa.Column('billing_state', sa.String(length=128), nullable=True))
    op.add_column('customers', sa.Column('billing_postal_code', sa.String(length=32), nullable=True))
    op.add_column('customers', sa.Column('billing_country', sa.String(length=64), nullable=True))
    op.add_column('customers', sa.Column('shipping_address_line1', sa.String(length=255), nullable=True))
    op.add_column('customers', sa.Column('shipping_city', sa.String(length=128), nullable=True))
    op.add_column('customers', sa.Column('shipping_state', sa.String(length=128), nullable=True))
    op.add_column('customers', sa.Column('shipping_postal_code', sa.String(length=32), nullable=True))
    op.add_column('customers', sa.Column('shipping_country', sa.String(length=64), nullable=True))
    op.add_column('customers', sa.Column('payment_terms_days', sa.Integer(), nullable=False, server_default='30'))
    op.add_column('customers', sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'))
    op.add_column('customers', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('customers', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('customers', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('customers', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.create_index(op.f('ix_customers_email'), 'customers', ['email'], unique=False)
    op.create_index(op.f('ix_customers_is_active'), 'customers', ['is_active'], unique=False)
    op.create_index(op.f('ix_customers_name'), 'customers', ['name'], unique=False)
    op.create_index(op.f('ix_customers_owner_user_id'), 'customers', ['owner_user_id'], unique=False)
    op.create_index(op.f('ix_customers_tier_id'), 'customers', ['tier_id'], unique=False)
    op.create_unique_constraint('uq_customers_code', 'customers', ['code'])
    op.create_foreign_key('fk_customers_owner_user', 'customers', 'users', ['owner_user_id'], ['id'], use_alter=True)
    op.add_column('categories', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('categories', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('categories', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('categories', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('categories', 'max_discount_pct',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=6, scale=2),
               existing_nullable=True)
    op.create_unique_constraint('uq_categories_name', 'categories', ['name'])
    op.add_column('products', sa.Column('sku', sa.String(length=64), nullable=True))
    op.add_column('products', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('cost', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'))
    op.add_column('products', sa.Column('unit', sa.String(length=32), nullable=False, server_default='unit'))
    op.add_column('products', sa.Column('tax_rate_pct', sa.Numeric(precision=6, scale=2), nullable=False, server_default='0'))
    op.add_column('products', sa.Column('product_type', sa.Enum('one_time', 'recurring', 'both', name='producttype_str', native_enum=False, length=32), nullable=False, server_default='one_time'))
    op.add_column('products', sa.Column('is_stocked', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('products', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('products', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('products', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('products', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('products', 'price',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=14, scale=2),
               existing_nullable=False)
    op.create_index(op.f('ix_products_category_id'), 'products', ['category_id'], unique=False)
    op.create_index(op.f('ix_products_is_active'), 'products', ['is_active'], unique=False)
    op.create_index(op.f('ix_products_is_archived'), 'products', ['is_archived'], unique=False)
    op.create_index(op.f('ix_products_name'), 'products', ['name'], unique=False)
    op.create_index(op.f('ix_products_sku'), 'products', ['sku'], unique=True)
    op.execute("UPDATE products SET cost = ROUND((price * (1 - COALESCE(unit_margin_pct, 0) / 100.0))::numeric, 2)")
    op.execute("UPDATE products SET sku = 'SKU-' || LPAD(id::text, 5, '0') WHERE sku IS NULL")
    op.drop_column('products', 'unit_margin_pct')
    op.create_index(op.f('ix_product_variants_product_id'), 'product_variants', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_variants_sku'), 'product_variants', ['sku'], unique=True)
    op.create_index(op.f('ix_price_lists_is_active'), 'price_lists', ['is_active'], unique=False)
    op.create_index(op.f('ix_price_lists_tier_id'), 'price_lists', ['tier_id'], unique=False)
    op.create_index(op.f('ix_price_list_items_price_list_id'), 'price_list_items', ['price_list_id'], unique=False)
    op.create_index(op.f('ix_price_list_items_product_id'), 'price_list_items', ['product_id'], unique=False)
    op.create_index(op.f('ix_discount_rules_category_id'), 'discount_rules', ['category_id'], unique=False)
    op.create_index(op.f('ix_discount_rules_is_active'), 'discount_rules', ['is_active'], unique=False)
    op.create_index(op.f('ix_discount_rules_product_id'), 'discount_rules', ['product_id'], unique=False)
    op.create_index(op.f('ix_discount_rules_scope'), 'discount_rules', ['scope'], unique=False)
    op.create_index(op.f('ix_discount_rules_tier_id'), 'discount_rules', ['tier_id'], unique=False)
    op.create_index(op.f('ix_approval_rules_is_active'), 'approval_rules', ['is_active'], unique=False)
    op.add_column('subscription_plans', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('subscription_plans', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('subscription_plans', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('subscription_plans', 'interval',
               existing_type=postgresql.ENUM('monthly', 'quarterly', 'yearly', name='billinginterval'),
               type_=sa.Enum('monthly', 'quarterly', 'yearly', name='billinginterval_str', native_enum=False, length=32),
               existing_nullable=False,
               postgresql_using='interval::text')
    op.alter_column('subscription_plans', 'price_per_interval',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=14, scale=2),
               existing_nullable=False)
    op.create_index(op.f('ix_subscription_plans_is_active'), 'subscription_plans', ['is_active'], unique=False)
    op.create_index(op.f('ix_subscription_plans_product_id'), 'subscription_plans', ['product_id'], unique=False)
    op.add_column('product_pairings', sa.Column('promotion_label', sa.String(length=128), nullable=True))
    op.add_column('product_pairings', sa.Column('promotion_start', sa.Date(), nullable=True))
    op.add_column('product_pairings', sa.Column('promotion_end', sa.Date(), nullable=True))
    op.add_column('product_pairings', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('product_pairings', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('product_pairings', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('product_pairings', 'co_purchase_score',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=6, scale=2),
               existing_nullable=False)
    op.create_index(op.f('ix_product_pairings_base_product_id'), 'product_pairings', ['base_product_id'], unique=False)
    op.create_index(op.f('ix_product_pairings_suggested_product_id'), 'product_pairings', ['suggested_product_id'], unique=False)
    op.create_unique_constraint('uq_product_pairing', 'product_pairings', ['base_product_id', 'suggested_product_id'])
    op.execute('DROP TYPE IF EXISTS billinginterval')
    op.execute("INSERT INTO approval_rules (name, approval_level, min_points_over, is_active, created_at, updated_at) VALUES ('Manager approval above 5 points', 'manager', 5, true, now(), now()), ('Finance approval above 15 points', 'manager_then_finance', 15, true, now(), now())")


def downgrade() -> None:
    op.drop_constraint('uq_product_pairing', 'product_pairings', type_='unique')
    op.drop_index(op.f('ix_product_pairings_suggested_product_id'), table_name='product_pairings')
    op.drop_index(op.f('ix_product_pairings_base_product_id'), table_name='product_pairings')
    op.drop_column('product_pairings', 'updated_at')
    op.drop_column('product_pairings', 'created_at')
    op.drop_column('product_pairings', 'is_active')
    op.drop_column('product_pairings', 'promotion_end')
    op.drop_column('product_pairings', 'promotion_start')
    op.drop_column('product_pairings', 'promotion_label')
    op.drop_index(op.f('ix_subscription_plans_product_id'), table_name='subscription_plans')
    op.drop_index(op.f('ix_subscription_plans_is_active'), table_name='subscription_plans')
    op.drop_column('subscription_plans', 'updated_at')
    op.drop_column('subscription_plans', 'created_at')
    op.drop_column('subscription_plans', 'is_active')
    op.drop_index(op.f('ix_approval_rules_is_active'), table_name='approval_rules')
    op.drop_index(op.f('ix_discount_rules_tier_id'), table_name='discount_rules')
    op.drop_index(op.f('ix_discount_rules_scope'), table_name='discount_rules')
    op.drop_index(op.f('ix_discount_rules_product_id'), table_name='discount_rules')
    op.drop_index(op.f('ix_discount_rules_is_active'), table_name='discount_rules')
    op.drop_index(op.f('ix_discount_rules_category_id'), table_name='discount_rules')
    op.drop_index(op.f('ix_price_list_items_product_id'), table_name='price_list_items')
    op.drop_index(op.f('ix_price_list_items_price_list_id'), table_name='price_list_items')
    op.drop_index(op.f('ix_price_lists_tier_id'), table_name='price_lists')
    op.drop_index(op.f('ix_price_lists_is_active'), table_name='price_lists')
    op.drop_index(op.f('ix_product_variants_sku'), table_name='product_variants')
    op.drop_index(op.f('ix_product_variants_product_id'), table_name='product_variants')
    op.add_column('products', sa.Column('unit_margin_pct', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True))
    op.drop_index(op.f('ix_products_sku'), table_name='products')
    op.drop_index(op.f('ix_products_name'), table_name='products')
    op.drop_index(op.f('ix_products_is_archived'), table_name='products')
    op.drop_index(op.f('ix_products_is_active'), table_name='products')
    op.drop_index(op.f('ix_products_category_id'), table_name='products')
    op.drop_column('products', 'updated_at')
    op.drop_column('products', 'created_at')
    op.drop_column('products', 'is_archived')
    op.drop_column('products', 'is_active')
    op.drop_column('products', 'is_stocked')
    op.drop_column('products', 'product_type')
    op.drop_column('products', 'tax_rate_pct')
    op.drop_column('products', 'unit')
    op.drop_column('products', 'cost')
    op.drop_column('products', 'description')
    op.drop_column('products', 'sku')
    op.drop_constraint('uq_categories_name', 'categories', type_='unique')
    op.drop_column('categories', 'updated_at')
    op.drop_column('categories', 'created_at')
    op.drop_column('categories', 'is_active')
    op.drop_column('categories', 'description')
    op.drop_constraint('fk_customers_owner_user', 'customers', type_='foreignkey')
    op.drop_constraint('uq_customers_code', 'customers', type_='unique')
    op.drop_index(op.f('ix_customers_tier_id'), table_name='customers')
    op.drop_index(op.f('ix_customers_owner_user_id'), table_name='customers')
    op.drop_index(op.f('ix_customers_name'), table_name='customers')
    op.drop_index(op.f('ix_customers_is_active'), table_name='customers')
    op.drop_index(op.f('ix_customers_email'), table_name='customers')
    op.drop_column('customers', 'updated_at')
    op.drop_column('customers', 'created_at')
    op.drop_column('customers', 'is_active')
    op.drop_column('customers', 'notes')
    op.drop_column('customers', 'currency')
    op.drop_column('customers', 'payment_terms_days')
    op.drop_column('customers', 'shipping_country')
    op.drop_column('customers', 'shipping_postal_code')
    op.drop_column('customers', 'shipping_state')
    op.drop_column('customers', 'shipping_city')
    op.drop_column('customers', 'shipping_address_line1')
    op.drop_column('customers', 'billing_country')
    op.drop_column('customers', 'billing_postal_code')
    op.drop_column('customers', 'billing_state')
    op.drop_column('customers', 'billing_city')
    op.drop_column('customers', 'billing_address_line1')
    op.drop_column('customers', 'contact_name')
    op.drop_column('customers', 'website')
    op.drop_column('customers', 'phone')
    op.drop_column('customers', 'email')
    op.drop_column('customers', 'industry')
    op.drop_column('customers', 'owner_user_id')
    op.drop_column('customers', 'code')
    op.drop_constraint('uq_customer_tiers_name', 'customer_tiers', type_='unique')
    op.drop_column('customer_tiers', 'updated_at')
    op.drop_column('customer_tiers', 'created_at')
    op.drop_column('customer_tiers', 'is_active')
    op.drop_column('customer_tiers', 'sort_order')
    op.drop_column('customer_tiers', 'description')
    op.drop_table('price_list_items')
    op.drop_table('product_variants')
    op.drop_table('discount_rules')
    op.drop_table('price_lists')
    op.drop_table('approval_rules')
