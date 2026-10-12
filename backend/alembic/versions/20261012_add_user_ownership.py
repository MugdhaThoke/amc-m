"""Add mandatory user ownership and tenant isolation

Revision ID: 20261012_add_user_ownership
Revises: None
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    # Step 1: Add tenant_id column (nullable initially)
    op.add_column(
        'chat_sessions',
        sa.Column('tenant_id', sa.String(36), nullable=True)
    )

    # Step 2: Update existing sessions with default user
    op.execute("""
        UPDATE chat_sessions 
        SET user_id = 'system_migration' 
        WHERE user_id IS NULL
    """)

    # Step 3: Make user_id NOT NULL
    op.alter_column(
        'chat_sessions',
        'user_id',
        existing_type=sa.String(36),
        nullable=False
    )

    # Step 4: Add indexes to chat_sessions
    op.create_index(
        'idx_session_user_tenant',
        'chat_sessions',
        ['user_id', 'tenant_id']
    )
    op.create_index(
        'idx_session_user_created',
        'chat_sessions',
        ['user_id', 'created_at']
    )

    # Step 5: Add user_id column to query_evidence and populate
    op.add_column(
        'query_evidence',
        sa.Column('user_id', sa.String(36), nullable=True)
    )
    op.execute("""
        UPDATE query_evidence 
        SET user_id = 'system_migration' 
        WHERE user_id IS NULL
    """)
    op.alter_column(
        'query_evidence',
        'user_id',
        existing_type=sa.String(36),
        nullable=False
    )

    # Step 6: Add tenant_id and indexes to query_evidence
    op.add_column(
        'query_evidence',
        sa.Column('tenant_id', sa.String(36), nullable=True)
    )
    op.create_index(
        'idx_qe_session_user',
        'query_evidence',
        ['session_id', 'user_id']
    )
    op.create_index(
        'idx_qe_user_session',
        'query_evidence',
        ['user_id', 'session_id']
    )
    op.create_index(
        'idx_qe_tenant_user',
        'query_evidence',
        ['tenant_id', 'user_id']
    )


def downgrade():
    op.drop_index('idx_qe_tenant_user', 'query_evidence')
    op.drop_index('idx_qe_user_session', 'query_evidence')
    op.drop_index('idx_qe_session_user', 'query_evidence')
    op.drop_column('query_evidence', 'tenant_id')
    op.drop_column('query_evidence', 'user_id')
    op.drop_index('idx_session_user_created', 'chat_sessions')
    op.drop_index('idx_session_user_tenant', 'chat_sessions')
    op.alter_column(
        'chat_sessions',
        'user_id',
        existing_type=sa.String(36),
        nullable=True
    )
    op.drop_column('chat_sessions', 'tenant_id')
