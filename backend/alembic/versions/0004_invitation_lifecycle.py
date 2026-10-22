"""Add declined state and release declined invitations for re-invites."""
from alembic import op
import sqlalchemy as sa

revision = "0004_invitation_lifecycle"
down_revision = "0003_workspaces"


def upgrade():
    op.add_column("workspace_invitations", sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True))
    # The old partial index regarded a declined invitation as open. Rebuild it
    # so a later invitation to the same address is allowed without duplicates.
    op.drop_index("uq_open_workspace_invitation", table_name="workspace_invitations")
    condition = sa.text("accepted_at IS NULL AND revoked_at IS NULL AND declined_at IS NULL")
    op.create_index("uq_open_workspace_invitation", "workspace_invitations", ["workspace_id", "email"], unique=True,
                    postgresql_where=condition, sqlite_where=condition)


def downgrade():
    raise RuntimeError("Destructive invitation lifecycle downgrade disabled. Restore a reviewed backup.")
