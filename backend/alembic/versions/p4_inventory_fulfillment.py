"""inventory reservations and movements, shipments, backorders, delivery promises

Revision ID: p4_inventory_fulfillment
Revises: p3_quotes_approvals
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

revision: str = 'p4_inventory_fulfillment'
down_revision: Union[str, Sequence[str], None] = 'p3_quotes_approvals'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('inventory_movements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('stock_id', sa.Integer(), nullable=False),
    sa.Column('warehouse_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('movement_type', sa.Enum('receipt', 'adjustment', 'reservation', 'release', 'consumption', name='movementtype_str', native_enum=False, length=32), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('on_hand_after', sa.Integer(), nullable=False),
    sa.Column('reserved_after', sa.Integer(), nullable=False),
    sa.Column('reference_type', sa.String(length=32), nullable=True),
    sa.Column('reference_id', sa.Integer(), nullable=True),
    sa.Column('actor_user_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ),
    sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('shipments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('shipment_number', sa.String(length=32), nullable=False),
    sa.Column('fulfillment_plan_id', sa.Integer(), nullable=False),
    sa.Column('quote_id', sa.Integer(), nullable=False),
    sa.Column('warehouse_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'shipped', 'delivered', name='shipmentstatus_str', native_enum=False, length=32), nullable=False),
    sa.Column('promised_date', sa.Date(), nullable=True),
    sa.Column('expected_date', sa.Date(), nullable=True),
    sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('tracking_reference', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['fulfillment_plan_id'], ['fulfillment_plans.id'], ),
    sa.ForeignKeyConstraint(['quote_id'], ['quotes.id'], ),
    sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('shipment_number')
    )
    op.add_column('warehouses', sa.Column('code', sa.String(length=16), nullable=True))
    op.add_column('warehouses', sa.Column('city', sa.String(length=128), nullable=True))
    op.add_column('warehouses', sa.Column('country', sa.String(length=64), nullable=True))
    op.add_column('warehouses', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('warehouses', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('warehouses', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('warehouses', 'shipping_cost_weight',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=6, scale=2),
               existing_nullable=False)
    op.create_index(op.f('ix_warehouses_is_active'), 'warehouses', ['is_active'], unique=False)
    op.create_unique_constraint('uq_warehouses_code', 'warehouses', ['code'])
    op.alter_column('stocks', 'quantity_available', new_column_name='quantity_on_hand')
    op.add_column('stocks', sa.Column('quantity_reserved', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('stocks', sa.Column('reorder_point', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('stocks', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('stocks', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.create_index(op.f('ix_stocks_product_id'), 'stocks', ['product_id'], unique=False)
    op.create_index(op.f('ix_stocks_warehouse_id'), 'stocks', ['warehouse_id'], unique=False)
    op.create_index(op.f('ix_inventory_movements_created_at'), 'inventory_movements', ['created_at'], unique=False)
    op.create_index(op.f('ix_inventory_movements_movement_type'), 'inventory_movements', ['movement_type'], unique=False)
    op.create_index(op.f('ix_inventory_movements_product_id'), 'inventory_movements', ['product_id'], unique=False)
    op.create_index(op.f('ix_inventory_movements_reference_id'), 'inventory_movements', ['reference_id'], unique=False)
    op.create_index(op.f('ix_inventory_movements_stock_id'), 'inventory_movements', ['stock_id'], unique=False)
    op.create_index(op.f('ix_inventory_movements_warehouse_id'), 'inventory_movements', ['warehouse_id'], unique=False)
    op.create_index(op.f('ix_shipments_fulfillment_plan_id'), 'shipments', ['fulfillment_plan_id'], unique=False)
    op.create_index(op.f('ix_shipments_quote_id'), 'shipments', ['quote_id'], unique=False)
    op.create_index(op.f('ix_shipments_status'), 'shipments', ['status'], unique=False)
    op.create_index(op.f('ix_shipments_warehouse_id'), 'shipments', ['warehouse_id'], unique=False)
    op.add_column('fulfillment_plans', sa.Column('expected_delivery_date', sa.Date(), nullable=True))
    op.add_column('fulfillment_plans', sa.Column('created_by_user_id', sa.Integer(), nullable=True))
    op.add_column('fulfillment_plans', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('fulfillment_plans', 'status',
               existing_type=postgresql.ENUM('suggested', 'confirmed', 'manually_overridden', name='fulfillmentplanstatus'),
               type_=sa.Enum('suggested', 'confirmed', 'manually_overridden', 'partially_shipped', 'shipped', 'cancelled', name='fulfillmentplanstatus_str', native_enum=False, length=32),
               existing_nullable=False,
               postgresql_using='status::text')
    op.alter_column('fulfillment_plans', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.create_index(op.f('ix_fulfillment_plans_quote_id'), 'fulfillment_plans', ['quote_id'], unique=False)
    op.create_index(op.f('ix_fulfillment_plans_status'), 'fulfillment_plans', ['status'], unique=False)
    op.create_foreign_key('fk_fulfillment_plans_created_by_user_id', 'fulfillment_plans', 'users', ['created_by_user_id'], ['id'])
    op.add_column('fulfillment_splits', sa.Column('status', sa.Enum('planned', 'reserved', 'shipped', 'backordered', 'cancelled', name='splitstatus_str', native_enum=False, length=32), nullable=False, server_default='planned'))
    op.add_column('fulfillment_splits', sa.Column('shipment_id', sa.Integer(), nullable=True))
    op.add_column('fulfillment_splits', sa.Column('expected_date', sa.Date(), nullable=True))
    op.create_index(op.f('ix_fulfillment_splits_fulfillment_plan_id'), 'fulfillment_splits', ['fulfillment_plan_id'], unique=False)
    op.create_index(op.f('ix_fulfillment_splits_quote_line_id'), 'fulfillment_splits', ['quote_line_id'], unique=False)
    op.create_index(op.f('ix_fulfillment_splits_shipment_id'), 'fulfillment_splits', ['shipment_id'], unique=False)
    op.create_index(op.f('ix_fulfillment_splits_status'), 'fulfillment_splits', ['status'], unique=False)
    op.create_index(op.f('ix_fulfillment_splits_warehouse_id'), 'fulfillment_splits', ['warehouse_id'], unique=False)
    op.create_foreign_key('fk_fulfillment_splits_shipment_id', 'fulfillment_splits', 'shipments', ['shipment_id'], ['id'])
    op.execute("UPDATE fulfillment_splits fs SET status = CASE WHEN fs.is_backorder THEN 'backordered' WHEN (SELECT fp.status FROM fulfillment_plans fp WHERE fp.id = fs.fulfillment_plan_id) IN ('confirmed', 'shipped') THEN 'shipped' ELSE 'planned' END")
    op.execute("UPDATE fulfillment_plans SET status = 'shipped' WHERE status = 'confirmed'")
    op.execute("UPDATE quotes q SET fulfillment_status = 'shipped' WHERE EXISTS (SELECT 1 FROM fulfillment_plans fp WHERE fp.quote_id = q.id AND fp.status = 'shipped')")
    op.execute('DROP TYPE IF EXISTS fulfillmentplanstatus')


def downgrade() -> None:
    op.drop_constraint('fk_fulfillment_splits_shipment_id', 'fulfillment_splits', type_='foreignkey')
    op.drop_index(op.f('ix_fulfillment_splits_warehouse_id'), table_name='fulfillment_splits')
    op.drop_index(op.f('ix_fulfillment_splits_status'), table_name='fulfillment_splits')
    op.drop_index(op.f('ix_fulfillment_splits_shipment_id'), table_name='fulfillment_splits')
    op.drop_index(op.f('ix_fulfillment_splits_quote_line_id'), table_name='fulfillment_splits')
    op.drop_index(op.f('ix_fulfillment_splits_fulfillment_plan_id'), table_name='fulfillment_splits')
    op.drop_column('fulfillment_splits', 'expected_date')
    op.drop_column('fulfillment_splits', 'shipment_id')
    op.drop_column('fulfillment_splits', 'status')
    op.drop_constraint('fk_fulfillment_plans_created_by_user_id', 'fulfillment_plans', type_='foreignkey')
    op.drop_index(op.f('ix_fulfillment_plans_status'), table_name='fulfillment_plans')
    op.drop_index(op.f('ix_fulfillment_plans_quote_id'), table_name='fulfillment_plans')
    op.drop_column('fulfillment_plans', 'updated_at')
    op.drop_column('fulfillment_plans', 'created_by_user_id')
    op.drop_column('fulfillment_plans', 'expected_delivery_date')
    op.drop_index(op.f('ix_shipments_warehouse_id'), table_name='shipments')
    op.drop_index(op.f('ix_shipments_status'), table_name='shipments')
    op.drop_index(op.f('ix_shipments_quote_id'), table_name='shipments')
    op.drop_index(op.f('ix_shipments_fulfillment_plan_id'), table_name='shipments')
    op.drop_index(op.f('ix_inventory_movements_warehouse_id'), table_name='inventory_movements')
    op.drop_index(op.f('ix_inventory_movements_stock_id'), table_name='inventory_movements')
    op.drop_index(op.f('ix_inventory_movements_reference_id'), table_name='inventory_movements')
    op.drop_index(op.f('ix_inventory_movements_product_id'), table_name='inventory_movements')
    op.drop_index(op.f('ix_inventory_movements_movement_type'), table_name='inventory_movements')
    op.drop_index(op.f('ix_inventory_movements_created_at'), table_name='inventory_movements')
    op.drop_index(op.f('ix_stocks_warehouse_id'), table_name='stocks')
    op.drop_index(op.f('ix_stocks_product_id'), table_name='stocks')
    op.drop_column('stocks', 'updated_at')
    op.drop_column('stocks', 'created_at')
    op.drop_column('stocks', 'reorder_point')
    op.drop_column('stocks', 'quantity_reserved')
    op.alter_column('stocks', 'quantity_on_hand', new_column_name='quantity_available')
    op.drop_constraint('uq_warehouses_code', 'warehouses', type_='unique')
    op.drop_index(op.f('ix_warehouses_is_active'), table_name='warehouses')
    op.drop_column('warehouses', 'updated_at')
    op.drop_column('warehouses', 'created_at')
    op.drop_column('warehouses', 'is_active')
    op.drop_column('warehouses', 'country')
    op.drop_column('warehouses', 'city')
    op.drop_column('warehouses', 'code')
    op.drop_table('shipments')
    op.drop_table('inventory_movements')
