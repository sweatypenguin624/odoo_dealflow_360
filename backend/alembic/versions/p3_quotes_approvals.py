"""quote numbering/versioning/totals, approval requests, audit v2, negotiation

Revision ID: p3_quotes_approvals
Revises: p2_catalog_pricing
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

revision: str = 'p3_quotes_approvals'
down_revision: Union[str, Sequence[str], None] = 'p2_catalog_pricing'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('approval_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('quote_id', sa.Integer(), nullable=False),
    sa.Column('quote_version', sa.Integer(), nullable=False),
    sa.Column('required_level', sa.String(length=32), nullable=False),
    sa.Column('status', sa.Enum('pending', 'approved', 'rejected', 'returned', 'superseded', 'expired', name='approvalrequeststatus_str', native_enum=False, length=32), nullable=False),
    sa.Column('current_step', sa.String(length=32), nullable=True),
    sa.Column('risk_summary', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['quote_id'], ['quotes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('quote_revisions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('quote_id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('reason', sa.String(length=255), nullable=True),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['quote_id'], ['quotes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.add_column('quotes', sa.Column('quote_number', sa.String(length=32), nullable=True))
    op.add_column('quotes', sa.Column('owner_user_id', sa.Integer(), nullable=True))
    op.add_column('quotes', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('quotes', sa.Column('approved_version', sa.Integer(), nullable=True))
    op.add_column('quotes', sa.Column('risk_score', sa.Numeric(precision=6, scale=2), nullable=True))
    op.add_column('quotes', sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'))
    op.add_column('quotes', sa.Column('order_discount_pct', sa.Numeric(precision=6, scale=2), nullable=False, server_default='0'))
    op.add_column('quotes', sa.Column('subtotal', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'))
    op.add_column('quotes', sa.Column('discount_total', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'))
    op.add_column('quotes', sa.Column('tax_total', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'))
    op.add_column('quotes', sa.Column('total', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'))
    op.add_column('quotes', sa.Column('margin_amount', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'))
    op.add_column('quotes', sa.Column('margin_pct', sa.Numeric(precision=6, scale=2), nullable=False, server_default='0'))
    op.add_column('quotes', sa.Column('valid_until', sa.Date(), nullable=True))
    op.add_column('quotes', sa.Column('promised_delivery_date', sa.Date(), nullable=True))
    op.add_column('quotes', sa.Column('expected_delivery_date', sa.Date(), nullable=True))
    op.add_column('quotes', sa.Column('actual_delivery_date', sa.Date(), nullable=True))
    op.add_column('quotes', sa.Column('order_number', sa.String(length=32), nullable=True))
    op.add_column('quotes', sa.Column('fulfillment_status', sa.Enum('not_started', 'planned', 'reserved', 'partially_shipped', 'shipped', 'delivered', name='fulfillmentstatus_str', native_enum=False, length=32), nullable=False, server_default='not_started'))
    op.add_column('quotes', sa.Column('billing_status', sa.Enum('not_billed', 'partially_billed', 'billed', 'paid', name='billingstatus_str', native_enum=False, length=32), nullable=False, server_default='not_billed'))
    op.add_column('quotes', sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('quotes', sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('quotes', sa.Column('last_activity_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('quotes', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('quotes', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('quotes', 'status',
               existing_type=postgresql.ENUM('draft', 'pending_approval', 'approved', 'rejected', 'confirmed', name='quotestatus'),
               type_=sa.Enum('draft', 'pending_approval', 'approved', 'rejected', 'revision_required', 'sent', 'under_negotiation', 'confirmed', 'expired', 'cancelled', name='quotestatus_str', native_enum=False, length=32),
               existing_nullable=False,
               postgresql_using='status::text')
    op.alter_column('quotes', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.create_index(op.f('ix_quotes_billing_status'), 'quotes', ['billing_status'], unique=False)
    op.create_index(op.f('ix_quotes_current_approval_step'), 'quotes', ['current_approval_step'], unique=False)
    op.create_index(op.f('ix_quotes_customer_id'), 'quotes', ['customer_id'], unique=False)
    op.create_index(op.f('ix_quotes_fulfillment_status'), 'quotes', ['fulfillment_status'], unique=False)
    op.create_index(op.f('ix_quotes_last_activity_at'), 'quotes', ['last_activity_at'], unique=False)
    op.create_index(op.f('ix_quotes_owner_user_id'), 'quotes', ['owner_user_id'], unique=False)
    op.create_index(op.f('ix_quotes_quote_number'), 'quotes', ['quote_number'], unique=True)
    op.create_index(op.f('ix_quotes_status'), 'quotes', ['status'], unique=False)
    op.create_unique_constraint('uq_quotes_order_number', 'quotes', ['order_number'])
    op.create_foreign_key('fk_quotes_owner_user_id', 'quotes', 'users', ['owner_user_id'], ['id'])
    op.execute("UPDATE quotes SET quote_number = 'Q-' || (10000 + id) WHERE quote_number IS NULL")
    op.execute("UPDATE quotes SET last_activity_at = created_at WHERE created_at IS NOT NULL")
    op.execute("UPDATE quotes SET approved_version = version WHERE status IN ('approved', 'confirmed')")
    op.execute("INSERT INTO number_sequences (name, prefix, next_value) SELECT 'quote', 'Q-', 10000 + COALESCE(MAX(id), 0) + 1 FROM quotes")
    op.drop_column('quotes', 'rep_name')
    op.add_column('quote_lines', sa.Column('variant_id', sa.Integer(), nullable=True))
    op.add_column('quote_lines', sa.Column('description', sa.String(length=255), nullable=True))
    op.add_column('quote_lines', sa.Column('unit_price', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'))
    op.add_column('quote_lines', sa.Column('unit_cost', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'))
    op.add_column('quote_lines', sa.Column('tax_rate_pct', sa.Numeric(precision=6, scale=2), nullable=False, server_default='0'))
    op.add_column('quote_lines', sa.Column('line_total', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'))
    op.add_column('quote_lines', sa.Column('subscription_plan_id', sa.Integer(), nullable=True))
    op.add_column('quote_lines', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('quote_lines', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('quote_lines', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('quote_lines', 'discount_pct',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=6, scale=2),
               existing_nullable=False)
    op.alter_column('quote_lines', 'line_value',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=14, scale=2),
               existing_nullable=False)
    op.create_index(op.f('ix_quote_lines_product_id'), 'quote_lines', ['product_id'], unique=False)
    op.create_index(op.f('ix_quote_lines_quote_id'), 'quote_lines', ['quote_id'], unique=False)
    op.create_foreign_key('fk_quote_lines_variant_id', 'quote_lines', 'product_variants', ['variant_id'], ['id'])
    op.create_foreign_key('fk_quote_lines_subscription_plan_id', 'quote_lines', 'subscription_plans', ['subscription_plan_id'], ['id'])
    op.execute("UPDATE quote_lines ql SET unit_price = CASE WHEN quantity > 0 THEN ROUND((line_value / quantity)::numeric, 2) ELSE 0 END, unit_cost = COALESCE((SELECT p.cost FROM products p WHERE p.id = ql.product_id), 0), tax_rate_pct = COALESCE((SELECT p.tax_rate_pct FROM products p WHERE p.id = ql.product_id), 0), description = (SELECT p.name FROM products p WHERE p.id = ql.product_id)")
    op.execute("UPDATE quote_lines SET line_total = ROUND((line_value * (1 - discount_pct / 100.0))::numeric, 2)")
    op.execute("UPDATE quotes q SET subtotal = s.subtotal, total = s.total, discount_total = s.subtotal - s.total, margin_amount = s.margin FROM (SELECT quote_id, COALESCE(SUM(line_value), 0) AS subtotal, COALESCE(SUM(line_total), 0) AS total, COALESCE(SUM(line_total - unit_cost * quantity), 0) AS margin FROM quote_lines GROUP BY quote_id) s WHERE s.quote_id = q.id")
    op.execute("UPDATE quotes SET margin_pct = CASE WHEN total > 0 THEN ROUND((margin_amount / total * 100)::numeric, 2) ELSE 0 END")
    op.create_index(op.f('ix_quote_revisions_quote_id'), 'quote_revisions', ['quote_id'], unique=False)
    op.create_index(op.f('ix_approval_requests_created_at'), 'approval_requests', ['created_at'], unique=False)
    op.create_index(op.f('ix_approval_requests_quote_id'), 'approval_requests', ['quote_id'], unique=False)
    op.create_index(op.f('ix_approval_requests_status'), 'approval_requests', ['status'], unique=False)
    op.add_column('approval_actions', sa.Column('approval_request_id', sa.Integer(), nullable=True))
    op.add_column('approval_actions', sa.Column('actor_user_id', sa.Integer(), nullable=True))
    op.alter_column('approval_actions', 'reason',
               existing_type=sa.VARCHAR(),
               type_=sa.Text(),
               existing_nullable=True)
    op.alter_column('approval_actions', 'timestamp',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('CURRENT_TIMESTAMP'))
    op.create_index(op.f('ix_approval_actions_actor_user_id'), 'approval_actions', ['actor_user_id'], unique=False)
    op.create_index(op.f('ix_approval_actions_approval_request_id'), 'approval_actions', ['approval_request_id'], unique=False)
    op.create_index(op.f('ix_approval_actions_quote_id'), 'approval_actions', ['quote_id'], unique=False)
    op.create_index(op.f('ix_approval_actions_timestamp'), 'approval_actions', ['timestamp'], unique=False)
    op.create_foreign_key('fk_approval_actions_approval_request_id', 'approval_actions', 'approval_requests', ['approval_request_id'], ['id'])
    op.create_foreign_key('fk_approval_actions_actor_user_id', 'approval_actions', 'users', ['actor_user_id'], ['id'])
    op.add_column('audit_logs', sa.Column('actor_user_id', sa.Integer(), nullable=True))
    op.add_column('audit_logs', sa.Column('entity_type', sa.String(length=64), nullable=True))
    op.add_column('audit_logs', sa.Column('entity_id', sa.Integer(), nullable=True))
    op.add_column('audit_logs', sa.Column('before_data', sa.JSON(), nullable=True))
    op.add_column('audit_logs', sa.Column('after_data', sa.JSON(), nullable=True))
    op.add_column('audit_logs', sa.Column('request_id', sa.String(length=32), nullable=True))
    op.alter_column('audit_logs', 'quote_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('audit_logs', 'reason',
               existing_type=sa.VARCHAR(),
               type_=sa.Text(),
               existing_nullable=True)
    op.alter_column('audit_logs', 'timestamp',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_actor_user_id'), 'audit_logs', ['actor_user_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_id'), 'audit_logs', ['entity_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_type'), 'audit_logs', ['entity_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_quote_id'), 'audit_logs', ['quote_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_timestamp'), 'audit_logs', ['timestamp'], unique=False)
    op.create_foreign_key('fk_audit_logs_actor_user_id', 'audit_logs', 'users', ['actor_user_id'], ['id'])
    op.add_column('portal_tokens', sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('portal_tokens', sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_portal_tokens_customer_id'), 'portal_tokens', ['customer_id'], unique=False)
    op.create_index(op.f('ix_portal_tokens_quote_id'), 'portal_tokens', ['quote_id'], unique=False)
    op.add_column('line_comments', sa.Column('author_user_id', sa.Integer(), nullable=True))
    op.add_column('line_comments', sa.Column('is_internal', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.alter_column('line_comments', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.create_index(op.f('ix_line_comments_created_at'), 'line_comments', ['created_at'], unique=False)
    op.create_index(op.f('ix_line_comments_quote_line_id'), 'line_comments', ['quote_line_id'], unique=False)
    op.create_foreign_key('fk_line_comments_author_user_id', 'line_comments', 'users', ['author_user_id'], ['id'])
    op.add_column('counter_proposals', sa.Column('message', sa.Text(), nullable=True))
    op.add_column('counter_proposals', sa.Column('approval_request_id', sa.Integer(), nullable=True))
    op.add_column('counter_proposals', sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True))
    op.alter_column('counter_proposals', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.create_index(op.f('ix_counter_proposals_created_at'), 'counter_proposals', ['created_at'], unique=False)
    op.create_index(op.f('ix_counter_proposals_quote_id'), 'counter_proposals', ['quote_id'], unique=False)
    op.create_index(op.f('ix_counter_proposals_status'), 'counter_proposals', ['status'], unique=False)
    op.create_foreign_key('fk_counter_proposals_approval_request_id', 'counter_proposals', 'approval_requests', ['approval_request_id'], ['id'])
    op.execute('DROP TYPE IF EXISTS quotestatus')


def downgrade() -> None:
    op.drop_constraint('fk_counter_proposals_approval_request_id', 'counter_proposals', type_='foreignkey')
    op.drop_index(op.f('ix_counter_proposals_status'), table_name='counter_proposals')
    op.drop_index(op.f('ix_counter_proposals_quote_id'), table_name='counter_proposals')
    op.drop_index(op.f('ix_counter_proposals_created_at'), table_name='counter_proposals')
    op.drop_column('counter_proposals', 'resolved_at')
    op.drop_column('counter_proposals', 'approval_request_id')
    op.drop_column('counter_proposals', 'message')
    op.drop_constraint('fk_line_comments_author_user_id', 'line_comments', type_='foreignkey')
    op.drop_index(op.f('ix_line_comments_quote_line_id'), table_name='line_comments')
    op.drop_index(op.f('ix_line_comments_created_at'), table_name='line_comments')
    op.drop_column('line_comments', 'is_internal')
    op.drop_column('line_comments', 'author_user_id')
    op.drop_index(op.f('ix_portal_tokens_quote_id'), table_name='portal_tokens')
    op.drop_index(op.f('ix_portal_tokens_customer_id'), table_name='portal_tokens')
    op.drop_column('portal_tokens', 'last_used_at')
    op.drop_column('portal_tokens', 'revoked_at')
    op.drop_constraint('fk_audit_logs_actor_user_id', 'audit_logs', type_='foreignkey')
    op.drop_index(op.f('ix_audit_logs_timestamp'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_quote_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_entity_type'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_entity_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_actor_user_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_column('audit_logs', 'request_id')
    op.drop_column('audit_logs', 'after_data')
    op.drop_column('audit_logs', 'before_data')
    op.drop_column('audit_logs', 'entity_id')
    op.drop_column('audit_logs', 'entity_type')
    op.drop_column('audit_logs', 'actor_user_id')
    op.drop_constraint('fk_approval_actions_actor_user_id', 'approval_actions', type_='foreignkey')
    op.drop_constraint('fk_approval_actions_approval_request_id', 'approval_actions', type_='foreignkey')
    op.drop_index(op.f('ix_approval_actions_timestamp'), table_name='approval_actions')
    op.drop_index(op.f('ix_approval_actions_quote_id'), table_name='approval_actions')
    op.drop_index(op.f('ix_approval_actions_approval_request_id'), table_name='approval_actions')
    op.drop_index(op.f('ix_approval_actions_actor_user_id'), table_name='approval_actions')
    op.drop_column('approval_actions', 'actor_user_id')
    op.drop_column('approval_actions', 'approval_request_id')
    op.drop_index(op.f('ix_approval_requests_status'), table_name='approval_requests')
    op.drop_index(op.f('ix_approval_requests_quote_id'), table_name='approval_requests')
    op.drop_index(op.f('ix_approval_requests_created_at'), table_name='approval_requests')
    op.drop_index(op.f('ix_quote_revisions_quote_id'), table_name='quote_revisions')
    op.drop_constraint('fk_quote_lines_subscription_plan_id', 'quote_lines', type_='foreignkey')
    op.drop_constraint('fk_quote_lines_variant_id', 'quote_lines', type_='foreignkey')
    op.drop_index(op.f('ix_quote_lines_quote_id'), table_name='quote_lines')
    op.drop_index(op.f('ix_quote_lines_product_id'), table_name='quote_lines')
    op.drop_column('quote_lines', 'updated_at')
    op.drop_column('quote_lines', 'created_at')
    op.drop_column('quote_lines', 'sort_order')
    op.drop_column('quote_lines', 'subscription_plan_id')
    op.drop_column('quote_lines', 'line_total')
    op.drop_column('quote_lines', 'tax_rate_pct')
    op.drop_column('quote_lines', 'unit_cost')
    op.drop_column('quote_lines', 'unit_price')
    op.drop_column('quote_lines', 'description')
    op.drop_column('quote_lines', 'variant_id')
    op.add_column('quotes', sa.Column('rep_name', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.drop_constraint('fk_quotes_owner_user_id', 'quotes', type_='foreignkey')
    op.drop_constraint('uq_quotes_order_number', 'quotes', type_='unique')
    op.drop_index(op.f('ix_quotes_status'), table_name='quotes')
    op.drop_index(op.f('ix_quotes_quote_number'), table_name='quotes')
    op.drop_index(op.f('ix_quotes_owner_user_id'), table_name='quotes')
    op.drop_index(op.f('ix_quotes_last_activity_at'), table_name='quotes')
    op.drop_index(op.f('ix_quotes_fulfillment_status'), table_name='quotes')
    op.drop_index(op.f('ix_quotes_customer_id'), table_name='quotes')
    op.drop_index(op.f('ix_quotes_current_approval_step'), table_name='quotes')
    op.drop_index(op.f('ix_quotes_billing_status'), table_name='quotes')
    op.drop_column('quotes', 'updated_at')
    op.drop_column('quotes', 'notes')
    op.drop_column('quotes', 'last_activity_at')
    op.drop_column('quotes', 'confirmed_at')
    op.drop_column('quotes', 'sent_at')
    op.drop_column('quotes', 'billing_status')
    op.drop_column('quotes', 'fulfillment_status')
    op.drop_column('quotes', 'order_number')
    op.drop_column('quotes', 'actual_delivery_date')
    op.drop_column('quotes', 'expected_delivery_date')
    op.drop_column('quotes', 'promised_delivery_date')
    op.drop_column('quotes', 'valid_until')
    op.drop_column('quotes', 'margin_pct')
    op.drop_column('quotes', 'margin_amount')
    op.drop_column('quotes', 'total')
    op.drop_column('quotes', 'tax_total')
    op.drop_column('quotes', 'discount_total')
    op.drop_column('quotes', 'subtotal')
    op.drop_column('quotes', 'order_discount_pct')
    op.drop_column('quotes', 'currency')
    op.drop_column('quotes', 'risk_score')
    op.drop_column('quotes', 'approved_version')
    op.drop_column('quotes', 'version')
    op.drop_column('quotes', 'owner_user_id')
    op.drop_column('quotes', 'quote_number')
    op.drop_table('quote_revisions')
    op.drop_table('approval_requests')
