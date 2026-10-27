"""Default-deny platform authorization; no user is promoted by migration."""
from alembic import op
import sqlalchemy as sa
revision = "0009_platform_admin"
down_revision = "0008_annotation_correction"
def upgrade():
    op.add_column("users", sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_users_created_at", "users", ["created_at"])
    op.create_index("ix_workspaces_created_at", "workspaces", ["created_at"])
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
def downgrade():
    raise RuntimeError("Restore a reviewed backup instead of removing administrative history.")
