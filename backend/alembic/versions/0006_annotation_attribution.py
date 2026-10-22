"""Preserve object identity and geometry while adding nullable attribution."""
from alembic import op
import sqlalchemy as sa

revision = "0006_annotation_attribution"
down_revision = "0005_email_delivery"


def upgrade():
    with op.batch_alter_table("annotations") as batch:
        batch.add_column(sa.Column("created_by", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("updated_by", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("source", sa.String(20), nullable=False, server_default="legacy"))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.create_foreign_key("fk_annotation_creator", "users", ["created_by"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_annotation_editor", "users", ["updated_by"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_annotations_created_by", ["created_by"])
        batch.create_index("ix_annotations_updated_by", ["updated_by"])
    if op.get_bind().dialect.name == "postgresql":
        # Old application timestamps were naive UTC, never local wall time.
        for column in ("created_at", "updated_at"):
            op.alter_column("annotations", column, type_=sa.DateTime(timezone=True),
                            postgresql_using=f"{column} AT TIME ZONE 'UTC'")


def downgrade():
    raise RuntimeError("Restore a reviewed backup instead of deleting annotation history.")
