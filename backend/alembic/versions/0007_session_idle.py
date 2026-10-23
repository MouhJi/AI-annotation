"""Separate real activity from token rotation timestamps."""
from alembic import op
import sqlalchemy as sa
revision = "0007_session_idle"
down_revision = "0006_annotation_attribution"

def upgrade():
    op.add_column("user_sessions", sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True))
    # No guessed activity grant on upgrade: use creation time, not background refresh.
    op.execute("UPDATE user_sessions SET last_activity_at = created_at")
    with op.batch_alter_table("user_sessions") as batch:
        batch.alter_column("last_activity_at", existing_type=sa.DateTime(timezone=True), nullable=False)

def downgrade():
    raise RuntimeError("Restore a reviewed backup instead of removing session policy.")
