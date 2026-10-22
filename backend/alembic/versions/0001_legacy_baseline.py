"""Non-destructive inspected baseline for the Phase 1-4 schema.

Existing tables are validated, never stamped, dropped or recreated.
"""
from alembic import op
import sqlalchemy as sa
revision = "0001_legacy"
down_revision = None

def upgrade():
    metadata = sa.MetaData()
    def integer(name, *args, **kwargs): return sa.Column(name, sa.Integer, *args, **kwargs)
    def timestamp(name): return sa.Column(name, sa.DateTime, nullable=False)
    sa.Table("projects", metadata, integer("id", primary_key=True), sa.Column("name", sa.String(120), nullable=False), sa.Column("description", sa.Text), sa.Column("annotation_mode", sa.String(32), server_default="object_detection"), timestamp("created_at"), timestamp("updated_at"))
    sa.Table("classes", metadata, integer("id", primary_key=True), integer("project_id", sa.ForeignKey("projects.id"), nullable=False, index=True), sa.Column("name", sa.String(80), nullable=False), timestamp("created_at"))
    sa.Table("images", metadata, integer("id", primary_key=True), integer("project_id", sa.ForeignKey("projects.id"), nullable=False, index=True), sa.Column("filename", sa.String(255), nullable=False), sa.Column("filepath", sa.String(500), nullable=False, unique=True), integer("width", nullable=False), integer("height", nullable=False), sa.Column("split", sa.String(10), index=True), timestamp("created_at"))
    sa.Table("annotations", metadata, integer("id", primary_key=True), integer("image_id", sa.ForeignKey("images.id"), nullable=False, index=True), integer("class_id", sa.ForeignKey("classes.id"), nullable=False), *[sa.Column(name, sa.Float, nullable=False) for name in ("x","y","width","height")], sa.Column("annotation_type", sa.String(16), server_default="bbox"), sa.Column("points_json", sa.Text), timestamp("created_at"), timestamp("updated_at"))
    sa.Table("project_class_mappings", metadata, integer("id", primary_key=True), integer("project_id", sa.ForeignKey("projects.id"), nullable=False, index=True), integer("model_class_id", nullable=False), sa.Column("model_class_name", sa.String(120), nullable=False), integer("class_id", sa.ForeignKey("classes.id"), nullable=False), timestamp("created_at"), timestamp("updated_at"), sa.UniqueConstraint("project_id", "model_class_id", name="uq_project_model_class"))
    sa.Table("auto_label_predictions", metadata, integer("id", primary_key=True), integer("image_id", sa.ForeignKey("images.id"), nullable=False, index=True), integer("model_class_id", nullable=False), sa.Column("model_class_name", sa.String(120), nullable=False), integer("mapped_class_id", sa.ForeignKey("classes.id")), *[sa.Column(name, sa.Float, nullable=False) for name in ("x","y","width","height","confidence")], sa.Column("prediction_type", sa.String(16), server_default="bbox"), sa.Column("points_json", sa.Text), sa.Column("status", sa.String(16), nullable=False, index=True), integer("annotation_id", sa.ForeignKey("annotations.id"), unique=True), timestamp("created_at"), timestamp("updated_at"))
    connection = op.get_bind()
    additions = {"projects": {"annotation_mode"}, "images": {"split"}, "annotations": {"annotation_type", "points_json"}, "auto_label_predictions": {"prediction_type", "points_json"}}
    for table in metadata.sorted_tables:
        inspector = sa.inspect(connection)
        if not inspector.has_table(table.name):
            table.create(connection)
            continue
        existing = {col["name"]: col for col in inspector.get_columns(table.name)}
        if not isinstance(existing["id"]["type"], sa.Integer): raise RuntimeError(f"Unexpected PK type in {table.name}; manual schema review required")
        for column in table.columns:
            if column.name in existing: continue
            if column.name not in additions.get(table.name, set()): raise RuntimeError(f"Unexpected legacy schema: missing {table.name}.{column.name}; baseline stopped")
            op.add_column(table.name, sa.Column(column.name, column.type, nullable=True, server_default=column.server_default))

def downgrade():
    raise RuntimeError("Baseline rollback is intentionally disabled to preserve legacy data")
