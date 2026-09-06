"""subscription billing schedule, invoice lines/statuses, payments and refunds

Revision ID: p5_subscriptions_invoices
Revises: p4_inventory_fulfillment
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

revision: str = 'p5_subscriptions_invoices'
down_revision: Union[str, Sequence[str], None] = 'p4_inventory_fulfillment'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('invoice_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('invoice_id', sa.Integer(), nullable=False),
    sa.Column('quote_line_id', sa.Integer(), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('discount_pct', sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column('tax_rate_pct', sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column('line_total', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('tax_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ),
    sa.ForeignKeyConstraint(['quote_line_id'], ['quote_lines.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.add_column('subscriptions', sa.Column('quote_id', sa.Integer(), nullable=True))
    op.add_column('subscriptions', sa.Column('customer_id', sa.Integer(), nullable=True))
    op.add_column('subscriptions', sa.Column('unit_price', sa.Numeric(precision=14, scale=2), nullable=True))
    op.add_column('subscriptions', sa.Column('start_date', sa.Date(), nullable=True))
    op.add_column('subscriptions', sa.Column('next_billing_date', sa.Date(), nullable=True))
    op.add_column('subscriptions', sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('subscriptions', sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('subscriptions', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('subscriptions', 'status',
               existing_type=postgresql.ENUM('active', 'cancelled', name='subscriptionstatus'),
               type_=sa.Enum('active', 'paused', 'cancelled', name='subscriptionstatus_str', native_enum=False, length=32),
               existing_nullable=False,
               postgresql_using='status::text')
    op.alter_column('subscriptions', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.create_index(op.f('ix_subscriptions_customer_id'), 'subscriptions', ['customer_id'], unique=False)
    op.create_index(op.f('ix_subscriptions_next_billing_date'), 'subscriptions', ['next_billing_date'], unique=False)
    op.create_index(op.f('ix_subscriptions_quote_id'), 'subscriptions', ['quote_id'], unique=False)
    op.create_index(op.f('ix_subscriptions_quote_line_id'), 'subscriptions', ['quote_line_id'], unique=False)
    op.create_index(op.f('ix_subscriptions_status'), 'subscriptions', ['status'], unique=False)
    op.create_index(op.f('ix_subscriptions_subscription_plan_id'), 'subscriptions', ['subscription_plan_id'], unique=False)
    op.create_foreign_key('fk_subscriptions_quote_id', 'subscriptions', 'quotes', ['quote_id'], ['id'])
    op.create_foreign_key('fk_subscriptions_customer_id', 'subscriptions', 'customers', ['customer_id'], ['id'])
    op.execute("UPDATE subscriptions s SET quote_id = (SELECT ql.quote_id FROM quote_lines ql WHERE ql.id = s.quote_line_id)")
    op.execute("UPDATE subscriptions s SET customer_id = (SELECT q.customer_id FROM quotes q WHERE q.id = s.quote_id)")
    op.execute("UPDATE subscriptions s SET unit_price = (SELECT p.price_per_interval FROM subscription_plans p WHERE p.id = s.subscription_plan_id), start_date = current_cycle_start, next_billing_date = CASE WHEN status = 'active' THEN current_cycle_end ELSE NULL END")
    op.add_column('billing_events', sa.Column('idempotency_key', sa.String(length=128), nullable=True))
    op.add_column('billing_events', sa.Column('invoice_id', sa.Integer(), nullable=True))
    op.add_column('billing_events', sa.Column('applied_to_invoice_id', sa.Integer(), nullable=True))
    op.alter_column('billing_events', 'event_type',
               existing_type=postgresql.ENUM('invoice', 'proration_charge', 'proration_credit', 'refund', 'cancellation_credit', name='billingeventtype'),
               type_=sa.Enum('invoice', 'proration_charge', 'proration_credit', 'refund', 'cancellation_credit', name='billingeventtype_str', native_enum=False, length=32),
               existing_nullable=False,
               postgresql_using='event_type::text')
    op.alter_column('billing_events', 'amount',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=14, scale=2),
               existing_nullable=False)
    op.alter_column('billing_events', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.create_index(op.f('ix_billing_events_event_date'), 'billing_events', ['event_date'], unique=False)
    op.create_index(op.f('ix_billing_events_event_type'), 'billing_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_billing_events_invoice_id'), 'billing_events', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_billing_events_subscription_id'), 'billing_events', ['subscription_id'], unique=False)
    op.create_unique_constraint('uq_billing_events_idempotency_key', 'billing_events', ['idempotency_key'])
    op.create_foreign_key('fk_billing_events_invoice_id', 'billing_events', 'invoices', ['invoice_id'], ['id'])
    op.create_foreign_key('fk_billing_events_applied_to_invoice_id', 'billing_events', 'invoices', ['applied_to_invoice_id'], ['id'])
    op.add_column('invoices', sa.Column('customer_id', sa.Integer(), nullable=True))
    op.add_column('invoices', sa.Column('fulfillment_plan_id', sa.Integer(), nullable=True))
    op.add_column('invoices', sa.Column('shipment_id', sa.Integer(), nullable=True))
    op.add_column('invoices', sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'))
    op.add_column('invoices', sa.Column('subtotal', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'))
    op.add_column('invoices', sa.Column('discount_total', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'))
    op.add_column('invoices', sa.Column('tax_total', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'))
    op.add_column('invoices', sa.Column('amount_paid', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'))
    op.add_column('invoices', sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('invoices', sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('invoices', sa.Column('void_reason', sa.Text(), nullable=True))
    op.add_column('invoices', sa.Column('billing_period_start', sa.Date(), nullable=True))
    op.add_column('invoices', sa.Column('billing_period_end', sa.Date(), nullable=True))
    op.add_column('invoices', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('invoices', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('invoices', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('invoices', 'invoice_type',
               existing_type=postgresql.ENUM('one_time', 'recurring', name='invoicetype'),
               type_=sa.Enum('one_time', 'recurring', name='invoicetype_str', native_enum=False, length=32),
               existing_nullable=False,
               postgresql_using='invoice_type::text')
    op.alter_column('invoices', 'status',
               existing_type=postgresql.ENUM('unpaid', 'paid', name='invoicestatus'),
               type_=sa.Enum('draft', 'issued', 'partially_paid', 'paid', 'overdue', 'void', name='invoicestatus_str', native_enum=False, length=32),
               existing_nullable=False,
               postgresql_using='status::text')
    op.alter_column('invoices', 'amount',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=14, scale=2),
               existing_nullable=False)
    op.alter_column('invoices', 'issued_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.create_index(op.f('ix_invoices_customer_id'), 'invoices', ['customer_id'], unique=False)
    op.create_index(op.f('ix_invoices_due_date'), 'invoices', ['due_date'], unique=False)
    op.create_index(op.f('ix_invoices_fulfillment_plan_id'), 'invoices', ['fulfillment_plan_id'], unique=False)
    op.create_index(op.f('ix_invoices_invoice_type'), 'invoices', ['invoice_type'], unique=False)
    op.create_index(op.f('ix_invoices_issued_at'), 'invoices', ['issued_at'], unique=False)
    op.create_index(op.f('ix_invoices_quote_id'), 'invoices', ['quote_id'], unique=False)
    op.create_index(op.f('ix_invoices_status'), 'invoices', ['status'], unique=False)
    op.create_index(op.f('ix_invoices_subscription_id'), 'invoices', ['subscription_id'], unique=False)
    op.create_unique_constraint('uq_invoices_shipment_id', 'invoices', ['shipment_id'])
    op.create_foreign_key('fk_invoices_shipment_id', 'invoices', 'shipments', ['shipment_id'], ['id'])
    op.create_foreign_key('fk_invoices_fulfillment_plan_id', 'invoices', 'fulfillment_plans', ['fulfillment_plan_id'], ['id'])
    op.create_foreign_key('fk_invoices_customer_id', 'invoices', 'customers', ['customer_id'], ['id'])
    op.execute("UPDATE invoices SET status = 'issued' WHERE status = 'unpaid'")
    op.execute("UPDATE invoices i SET customer_id = (SELECT q.customer_id FROM quotes q WHERE q.id = i.quote_id), subtotal = amount")
    op.execute("UPDATE invoices i SET amount_paid = COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.invoice_id = i.id), 0)")
    op.execute("UPDATE invoices SET paid_at = issued_at WHERE status = 'paid' AND paid_at IS NULL")
    op.execute("INSERT INTO number_sequences (name, prefix, next_value) SELECT 'invoice', 'INV-', GREATEST(10001, COALESCE(MAX(NULLIF(REGEXP_REPLACE(invoice_number, '[^0-9]', '', 'g'), '')::int), 0) + 1) FROM invoices")
    op.create_index(op.f('ix_invoice_lines_invoice_id'), 'invoice_lines', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_invoice_lines_quote_line_id'), 'invoice_lines', ['quote_line_id'], unique=False)
    op.add_column('payments', sa.Column('payment_number', sa.String(length=32), nullable=True))
    op.add_column('payments', sa.Column('customer_id', sa.Integer(), nullable=True))
    op.add_column('payments', sa.Column('direction', sa.Enum('payment', 'refund', name='paymentdirection_str', native_enum=False, length=32), nullable=False, server_default='payment'))
    op.add_column('payments', sa.Column('reference', sa.String(length=128), nullable=True))
    op.add_column('payments', sa.Column('status', sa.Enum('pending', 'completed', 'failed', name='paymentstatus_str', native_enum=False, length=32), nullable=False, server_default='completed'))
    op.add_column('payments', sa.Column('provider', sa.String(length=32), nullable=False, server_default='manual'))
    op.add_column('payments', sa.Column('provider_reference', sa.String(length=128), nullable=True))
    op.add_column('payments', sa.Column('recorded_by_user_id', sa.Integer(), nullable=True))
    op.add_column('payments', sa.Column('idempotency_key', sa.String(length=128), nullable=True))
    op.add_column('payments', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('payments', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('payments', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('payments', 'amount',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=14, scale=2),
               existing_nullable=False)
    op.alter_column('payments', 'paid_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.create_index(op.f('ix_payments_customer_id'), 'payments', ['customer_id'], unique=False)
    op.create_index(op.f('ix_payments_direction'), 'payments', ['direction'], unique=False)
    op.create_index(op.f('ix_payments_invoice_id'), 'payments', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_payments_paid_at'), 'payments', ['paid_at'], unique=False)
    op.create_index(op.f('ix_payments_reference'), 'payments', ['reference'], unique=False)
    op.create_index(op.f('ix_payments_status'), 'payments', ['status'], unique=False)
    op.create_unique_constraint('uq_payments_idempotency_key', 'payments', ['idempotency_key'])
    op.create_unique_constraint('uq_payments_payment_number', 'payments', ['payment_number'])
    op.create_foreign_key('fk_payments_customer_id', 'payments', 'customers', ['customer_id'], ['id'])
    op.create_foreign_key('fk_payments_recorded_by_user_id', 'payments', 'users', ['recorded_by_user_id'], ['id'])
    op.execute("UPDATE payments SET payment_number = 'PAY-' || (10000 + id) WHERE payment_number IS NULL")
    op.execute("INSERT INTO number_sequences (name, prefix, next_value) SELECT 'payment', 'PAY-', 10000 + COALESCE(MAX(id), 0) + 1 FROM payments")
    op.execute('DROP TYPE IF EXISTS subscriptionstatus')
    op.execute('DROP TYPE IF EXISTS billingeventtype')
    op.execute('DROP TYPE IF EXISTS invoicetype')
    op.execute('DROP TYPE IF EXISTS invoicestatus')


def downgrade() -> None:
    op.drop_constraint('fk_payments_recorded_by_user_id', 'payments', type_='foreignkey')
    op.drop_constraint('fk_payments_customer_id', 'payments', type_='foreignkey')
    op.drop_constraint('uq_payments_payment_number', 'payments', type_='unique')
    op.drop_constraint('uq_payments_idempotency_key', 'payments', type_='unique')
    op.drop_index(op.f('ix_payments_status'), table_name='payments')
    op.drop_index(op.f('ix_payments_reference'), table_name='payments')
    op.drop_index(op.f('ix_payments_paid_at'), table_name='payments')
    op.drop_index(op.f('ix_payments_invoice_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_direction'), table_name='payments')
    op.drop_index(op.f('ix_payments_customer_id'), table_name='payments')
    op.drop_column('payments', 'updated_at')
    op.drop_column('payments', 'created_at')
    op.drop_column('payments', 'notes')
    op.drop_column('payments', 'idempotency_key')
    op.drop_column('payments', 'recorded_by_user_id')
    op.drop_column('payments', 'provider_reference')
    op.drop_column('payments', 'provider')
    op.drop_column('payments', 'status')
    op.drop_column('payments', 'reference')
    op.drop_column('payments', 'direction')
    op.drop_column('payments', 'customer_id')
    op.drop_column('payments', 'payment_number')
    op.drop_index(op.f('ix_invoice_lines_quote_line_id'), table_name='invoice_lines')
    op.drop_index(op.f('ix_invoice_lines_invoice_id'), table_name='invoice_lines')
    op.drop_constraint('fk_invoices_customer_id', 'invoices', type_='foreignkey')
    op.drop_constraint('fk_invoices_fulfillment_plan_id', 'invoices', type_='foreignkey')
    op.drop_constraint('fk_invoices_shipment_id', 'invoices', type_='foreignkey')
    op.drop_constraint('uq_invoices_shipment_id', 'invoices', type_='unique')
    op.drop_index(op.f('ix_invoices_subscription_id'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_status'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_quote_id'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_issued_at'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_invoice_type'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_fulfillment_plan_id'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_due_date'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_customer_id'), table_name='invoices')
    op.drop_column('invoices', 'updated_at')
    op.drop_column('invoices', 'created_at')
    op.drop_column('invoices', 'notes')
    op.drop_column('invoices', 'billing_period_end')
    op.drop_column('invoices', 'billing_period_start')
    op.drop_column('invoices', 'void_reason')
    op.drop_column('invoices', 'voided_at')
    op.drop_column('invoices', 'paid_at')
    op.drop_column('invoices', 'amount_paid')
    op.drop_column('invoices', 'tax_total')
    op.drop_column('invoices', 'discount_total')
    op.drop_column('invoices', 'subtotal')
    op.drop_column('invoices', 'currency')
    op.drop_column('invoices', 'shipment_id')
    op.drop_column('invoices', 'fulfillment_plan_id')
    op.drop_column('invoices', 'customer_id')
    op.drop_constraint('fk_billing_events_applied_to_invoice_id', 'billing_events', type_='foreignkey')
    op.drop_constraint('fk_billing_events_invoice_id', 'billing_events', type_='foreignkey')
    op.drop_constraint('uq_billing_events_idempotency_key', 'billing_events', type_='unique')
    op.drop_index(op.f('ix_billing_events_subscription_id'), table_name='billing_events')
    op.drop_index(op.f('ix_billing_events_invoice_id'), table_name='billing_events')
    op.drop_index(op.f('ix_billing_events_event_type'), table_name='billing_events')
    op.drop_index(op.f('ix_billing_events_event_date'), table_name='billing_events')
    op.drop_column('billing_events', 'applied_to_invoice_id')
    op.drop_column('billing_events', 'invoice_id')
    op.drop_column('billing_events', 'idempotency_key')
    op.drop_constraint('fk_subscriptions_customer_id', 'subscriptions', type_='foreignkey')
    op.drop_constraint('fk_subscriptions_quote_id', 'subscriptions', type_='foreignkey')
    op.drop_index(op.f('ix_subscriptions_subscription_plan_id'), table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_status'), table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_quote_line_id'), table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_quote_id'), table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_next_billing_date'), table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_customer_id'), table_name='subscriptions')
    op.drop_column('subscriptions', 'updated_at')
    op.drop_column('subscriptions', 'cancelled_at')
    op.drop_column('subscriptions', 'paused_at')
    op.drop_column('subscriptions', 'next_billing_date')
    op.drop_column('subscriptions', 'start_date')
    op.drop_column('subscriptions', 'unit_price')
    op.drop_column('subscriptions', 'customer_id')
    op.drop_column('subscriptions', 'quote_id')
    op.drop_table('invoice_lines')
