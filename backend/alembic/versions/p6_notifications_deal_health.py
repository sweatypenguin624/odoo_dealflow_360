"""notifications, email log, deal-health alerts and actions

Revision ID: p6_notifications_deal_health
Revises: p5_subscriptions_invoices
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

revision: str = 'p6_notifications_deal_health'
down_revision: Union[str, Sequence[str], None] = 'p5_subscriptions_invoices'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('email_messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('to_address', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('body_text', sa.Text(), nullable=False),
    sa.Column('template', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('entity_type', sa.String(length=32), nullable=True),
    sa.Column('entity_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('recipient_user_id', sa.Integer(), nullable=False),
    sa.Column('triggered_by_user_id', sa.Integer(), nullable=True),
    sa.Column('type', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('entity_type', sa.String(length=32), nullable=True),
    sa.Column('entity_id', sa.Integer(), nullable=True),
    sa.Column('is_read', sa.Boolean(), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['recipient_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['triggered_by_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('deal_health_alerts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('quote_id', sa.Integer(), nullable=False),
    sa.Column('alert_type', sa.String(length=32), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('status', sa.Enum('open', 'acknowledged', 'resolved', name='alertstatus_str', native_enum=False, length=32), nullable=False),
    sa.Column('dedupe_key', sa.String(length=128), nullable=False),
    sa.Column('entity_type', sa.String(length=32), nullable=False),
    sa.Column('entity_id', sa.Integer(), nullable=False),
    sa.Column('details', sa.JSON(), nullable=True),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('acknowledged_by_user_id', sa.Integer(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_by_user_id', sa.Integer(), nullable=True),
    sa.Column('resolution_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['acknowledged_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['quote_id'], ['quotes.id'], ),
    sa.ForeignKeyConstraint(['resolved_by_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('notification_deliveries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('notification_id', sa.Integer(), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('recipient_address', sa.String(length=255), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('deal_health_actions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('alert_id', sa.Integer(), nullable=False),
    sa.Column('action_type', sa.String(length=32), nullable=False),
    sa.Column('actor_user_id', sa.Integer(), nullable=True),
    sa.Column('actor_label', sa.String(length=255), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('recipients', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['alert_id'], ['deal_health_alerts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)
    op.create_index(op.f('ix_notifications_is_read'), 'notifications', ['is_read'], unique=False)
    op.create_index(op.f('ix_notifications_recipient_user_id'), 'notifications', ['recipient_user_id'], unique=False)
    op.create_index(op.f('ix_notifications_type'), 'notifications', ['type'], unique=False)
    op.create_index(op.f('ix_notification_deliveries_notification_id'), 'notification_deliveries', ['notification_id'], unique=False)
    op.create_index(op.f('ix_email_messages_created_at'), 'email_messages', ['created_at'], unique=False)
    op.create_index(op.f('ix_email_messages_entity_id'), 'email_messages', ['entity_id'], unique=False)
    op.create_index(op.f('ix_email_messages_status'), 'email_messages', ['status'], unique=False)
    op.create_index(op.f('ix_email_messages_template'), 'email_messages', ['template'], unique=False)
    op.create_index(op.f('ix_email_messages_to_address'), 'email_messages', ['to_address'], unique=False)
    op.create_index(op.f('ix_deal_health_alerts_alert_type'), 'deal_health_alerts', ['alert_type'], unique=False)
    op.create_index(op.f('ix_deal_health_alerts_dedupe_key'), 'deal_health_alerts', ['dedupe_key'], unique=False)
    op.create_index(op.f('ix_deal_health_alerts_quote_id'), 'deal_health_alerts', ['quote_id'], unique=False)
    op.create_index(op.f('ix_deal_health_alerts_severity'), 'deal_health_alerts', ['severity'], unique=False)
    op.create_index(op.f('ix_deal_health_alerts_status'), 'deal_health_alerts', ['status'], unique=False)
    op.create_index(op.f('ix_deal_health_actions_alert_id'), 'deal_health_actions', ['alert_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_deal_health_actions_alert_id'), table_name='deal_health_actions')
    op.drop_index(op.f('ix_deal_health_alerts_status'), table_name='deal_health_alerts')
    op.drop_index(op.f('ix_deal_health_alerts_severity'), table_name='deal_health_alerts')
    op.drop_index(op.f('ix_deal_health_alerts_quote_id'), table_name='deal_health_alerts')
    op.drop_index(op.f('ix_deal_health_alerts_dedupe_key'), table_name='deal_health_alerts')
    op.drop_index(op.f('ix_deal_health_alerts_alert_type'), table_name='deal_health_alerts')
    op.drop_index(op.f('ix_email_messages_to_address'), table_name='email_messages')
    op.drop_index(op.f('ix_email_messages_template'), table_name='email_messages')
    op.drop_index(op.f('ix_email_messages_status'), table_name='email_messages')
    op.drop_index(op.f('ix_email_messages_entity_id'), table_name='email_messages')
    op.drop_index(op.f('ix_email_messages_created_at'), table_name='email_messages')
    op.drop_index(op.f('ix_notification_deliveries_notification_id'), table_name='notification_deliveries')
    op.drop_index(op.f('ix_notifications_type'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_recipient_user_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_is_read'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_created_at'), table_name='notifications')
    op.drop_table('deal_health_actions')
    op.drop_table('notification_deliveries')
    op.drop_table('deal_health_alerts')
    op.drop_table('notifications')
    op.drop_table('email_messages')
