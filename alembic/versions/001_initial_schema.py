"""Initial schema matching current models.

Revision ID: 001
Revises: None
Create Date: 2026-03-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vendor_master",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("vendor_name", sa.String(255), nullable=False),
        sa.Column("address", sa.String(500)),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(100)),
        sa.Column("zip", sa.String(20)),
        sa.Column("country", sa.String(100), server_default="US"),
        sa.Column("tax_id", sa.String(20)),
        sa.Column(
            "status",
            sa.Enum("active", "inactive", "duplicate", name="vendor_status"),
            server_default="active",
        ),
        sa.Column("cluster_id", sa.Integer, index=True),
        sa.Column("source", sa.String(100)),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("vendor_id", sa.Integer, sa.ForeignKey("vendor_master.id", ondelete="SET NULL")),
        sa.Column("details_json", sa.JSON),
        sa.Column("confidence", sa.Float),
        sa.Column("timestamp", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "analyst_overrides",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("vendor_id", sa.Integer, sa.ForeignKey("vendor_master.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_action", sa.String(100), nullable=False),
        sa.Column("override_action", sa.String(100), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("analyst_name", sa.String(100)),
        sa.Column("timestamp", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("analyst_overrides")
    op.drop_table("audit_log")
    op.drop_table("vendor_master")
