"""Add review workflow without approving or inventing provenance for legacy data."""
from alembic import op
import sqlalchemy as sa
revision = "0010_annotation_quality"
down_revision = "0009_platform_admin"


def upgrade():
    op.add_column("auto_label_predictions", sa.Column("human_edited", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("projects", sa.Column("require_review", sa.Boolean(), nullable=False, server_default=sa.false()))
    for column in [sa.Column("review_state", sa.String(24), nullable=False, server_default="not_started"),
                   sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
                   sa.Column("review_version", sa.Integer(), nullable=False, server_default="0"),
                   sa.Column("approved_revision", sa.Integer()),
                   sa.Column("negative_confirmed", sa.Boolean(), nullable=False, server_default=sa.false())]:
        op.add_column("images", column)
    op.create_index("ix_images_review_state", "images", ["review_state"])
    op.execute("UPDATE images SET review_state='in_progress', revision=1 WHERE EXISTS (SELECT 1 FROM annotations WHERE annotations.image_id=images.id AND annotations.deleted_at IS NULL)")
    op.create_check_constraint("ck_images_review_state", "images", "review_state IN ('not_started','in_progress','pending_review','changes_requested','approved')") if op.get_bind().dialect.name != "sqlite" else None
    # Use the same model metadata for portable UUID and JSON column types.
    from app.models.quality import ImageRevision, ReviewEvent, CommentThread, ReviewComment, ActivityCursor, AnnotationActivity
    for model in [ImageRevision, ReviewEvent, CommentThread, ReviewComment, ActivityCursor, AnnotationActivity]:
        model.__table__.create(op.get_bind())
    op.create_index("ix_review_queue", "images", ["project_id", "review_state", "id"])
    op.create_index("ix_review_event_image_action", "review_events", ["image_id", "action", "id"])


def downgrade():
    raise RuntimeError("Restore a reviewed backup instead of deleting review history.")
