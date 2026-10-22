"""Authentication tables and nullable transitional ownership. No owner assignment."""
from alembic import op
import sqlalchemy as sa
revision = "0002_auth"
down_revision = "0001_legacy"

def timestamps():
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]

def upgrade():
    op.create_table("users", sa.Column("id", sa.Uuid, primary_key=True), sa.Column("email", sa.String(255), nullable=False), sa.Column("password_hash", sa.Text, nullable=False), sa.Column("full_name", sa.String(150), nullable=False), sa.Column("avatar_key", sa.Text), sa.Column("status", sa.String(20), nullable=False, server_default="active"), sa.Column("email_verified_at", sa.DateTime(timezone=True)), *timestamps(), sa.Column("last_login_at", sa.DateTime(timezone=True)), sa.CheckConstraint("status IN ('active','disabled','pending_verification')", name="ck_user_status"))
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table("user_sessions", sa.Column("id", sa.Uuid, primary_key=True), sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False), sa.Column("refresh_token_hash", sa.String(64), nullable=False, unique=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("revoked_at", sa.DateTime(timezone=True)), sa.Column("last_used_at", sa.DateTime(timezone=True)), sa.Column("user_agent", sa.Text), sa.Column("device_name", sa.String(150)))
    op.create_table("used_refresh_tokens", sa.Column("token_hash", sa.String(64), primary_key=True), sa.Column("session_id", sa.Uuid, sa.ForeignKey("user_sessions.id"), nullable=False), sa.Column("used_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_used_refresh_tokens_session_id", "used_refresh_tokens", ["session_id"])
    for table in ("password_reset_tokens", "email_verification_tokens"):
        op.create_table(table, sa.Column("id", sa.Uuid, primary_key=True), sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("used_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for table in ("user_sessions", "password_reset_tokens", "email_verification_tokens"):
        for column in ("user_id", "expires_at"): op.create_index(f"ix_{table}_{column}", table, [column])
    # SQLite needs batch mode for ALTER constraints; on PostgreSQL this is a normal
    # additive ALTER TABLE, preserving every existing project/image/annotation row.
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("owner_user_id", sa.Uuid, nullable=True))
        batch.create_foreign_key("fk_projects_owner_user", "users", ["owner_user_id"], ["id"])
        batch.create_index("ix_projects_owner_user_id", ["owner_user_id"])

def downgrade():
    raise RuntimeError("Auth rollback is intentionally disabled: restore a reviewed backup instead")
