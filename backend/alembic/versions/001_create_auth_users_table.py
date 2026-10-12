"""Create auth_users table - database-backed user store

Revision ID: 001_create_auth_users
Revises: 
Create Date: 2026-10-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '001_create_auth_users'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'auth_users',
        sa.Column('username', sa.String(128), nullable=False),
        sa.Column('password_hash', sa.String(256), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False),
        sa.Column('email', sa.String(256), nullable=False),
        sa.Column('role', sa.String(128), nullable=False),
        sa.Column('department', sa.String(256), nullable=False, server_default=''),
        sa.Column('avatar_initials', sa.String(10), nullable=False, server_default=''),
        sa.Column('status', sa.String(20), nullable=False, server_default='Active'),
        sa.Column('tenant_id', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.Column('last_login_ip', sa.String(45), nullable=True),
        sa.PrimaryKeyConstraint('username')
    )
    
    # Create indexes
    op.create_index('idx_auth_users_email', 'auth_users', ['email'])
    op.create_index('idx_auth_users_role', 'auth_users', ['role'])
    op.create_index('idx_auth_users_status', 'auth_users', ['status'])
    op.create_index('idx_auth_users_tenant', 'auth_users', ['tenant_id'])
    op.create_index('idx_auth_users_created', 'auth_users', ['created_at'])


def downgrade() -> None:
    op.drop_table('auth_users')
