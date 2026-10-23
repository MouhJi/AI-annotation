from alembic import op
import sqlalchemy as sa
revision = "0008_annotation_correction"
down_revision = "0007_session_idle"
def upgrade():
    with op.batch_alter_table("annotations") as batch:
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("deleted_by", sa.Uuid()))
        batch.create_foreign_key("fk_annotation_deleted_by", "users", ["deleted_by"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_annotations_deleted_at", ["deleted_at"])
def downgrade():
    raise RuntimeError("Restore a reviewed backup instead of removing deletion history.")
