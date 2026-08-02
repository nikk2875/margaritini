"""add node descriptions

Revision ID: bf39a5c1d2e4
Revises: 09d7f71e5caa
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa

revision = "bf39a5c1d2e4"
down_revision = "09d7f71e5caa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.add_column(
            sa.Column("description", sa.String(length=5000), nullable=False, server_default="")
        )


def downgrade() -> None:
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.drop_column("description")
