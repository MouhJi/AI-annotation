"""Additive workspace schema only. Explicit dry-run/backfill is a separate command."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_workspaces"
down_revision = "0002_auth"

def upgrade():
    op.create_table("workspaces",
        sa.Column("id", sa.Uuid, primary_key=True), sa.Column("name", sa.String(150), nullable=False),
        sa.Column("slug", sa.String(160), nullable=False, unique=True), sa.Column("description", sa.Text),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("personal_user_id", sa.Uuid, sa.ForeignKey("users.id"), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("workspace_members",
        sa.Column("id", sa.Uuid, primary_key=True), sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False), sa.Column("role", sa.String(30), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("invited_by", sa.Uuid, sa.ForeignKey("users.id")),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
        sa.CheckConstraint("role IN ('owner','admin','annotator','reviewer','viewer')", name="ck_member_role"))
    op.create_table("workspace_invitations",
        sa.Column("id", sa.Uuid, primary_key=True), sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False), sa.Column("role", sa.String(30), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("invited_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)), sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('owner','admin','annotator','reviewer','viewer')", name="ck_invitation_role"))
    condition = sa.text("accepted_at IS NULL AND revoked_at IS NULL")
    op.create_index("uq_open_workspace_invitation", "workspace_invitations", ["workspace_id", "email"], unique=True, postgresql_where=condition, sqlite_where=condition)
    op.create_table("audit_logs",
        sa.Column("id", sa.Uuid, primary_key=True), sa.Column("workspace_id", sa.Uuid), sa.Column("actor_user_id", sa.Uuid),
        sa.Column("action", sa.String(100), nullable=False), sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=False),
        sa.Column("metadata", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for table, columns in {"workspace_members": ["workspace_id", "user_id"], "workspace_invitations": ["workspace_id", "expires_at"], "audit_logs": ["workspace_id", "created_at"]}.items():
        for col in columns: op.create_index(f"ix_{table}_{col}", table, [col])
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("workspace_id", sa.Uuid, nullable=True))
        batch.create_foreign_key("fk_projects_workspace", "workspaces", ["workspace_id"], ["id"])
        batch.create_index("ix_projects_workspace_id", ["workspace_id"])

def downgrade():
    raise RuntimeError("Destructive workspace downgrade disabled. Restore a reviewed backup; see PHASE6_WORKSPACES.md")
