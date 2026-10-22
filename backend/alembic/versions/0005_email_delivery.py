"""Track mail attempts without persisting message bodies or plaintext tokens."""
from alembic import op
import sqlalchemy as sa

revision = "0005_email_delivery"
down_revision = "0004_invitation_lifecycle"


def upgrade():
    op.create_table("email_delivery_attempts",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('prepared','sending','sent','development','failed')", name="ck_email_delivery_status"))
    op.create_index("ix_email_delivery_resource", "email_delivery_attempts", ["purpose", "resource_id"])


def downgrade():
    raise RuntimeError("Restore a reviewed backup instead of deleting delivery history.")
