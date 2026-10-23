import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session, with_loader_criteria
from sqlalchemy import event
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./annotation.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine_options = {"connect_args": connect_args}
if DATABASE_URL in {"sqlite://", "sqlite:///:memory:"}:
    engine_options["poolclass"] = StaticPool
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

@event.listens_for(Session, "do_orm_execute")
def exclude_deleted_annotations(state):
    if state.is_select and not state.execution_options.get("include_deleted"):
        from .models import Annotation
        state.statement = state.statement.options(with_loader_criteria(Annotation, lambda row: row.deleted_at.is_(None), include_aliases=True))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def ensure_schema() -> None:
    """Apply the additive MVP migration needed by existing local databases."""
    inspector = inspect(engine)
    additions = {
        "images": {"split": "VARCHAR(10)"},
        "projects": {"annotation_mode": "VARCHAR(32) DEFAULT 'object_detection'"},
        "annotations": {"annotation_type": "VARCHAR(16) DEFAULT 'bbox'", "points_json": "TEXT"},
        "auto_label_predictions": {"prediction_type": "VARCHAR(16) DEFAULT 'bbox'", "points_json": "TEXT"},
    }
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns_to_add in additions.items():
            if table not in tables: continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for column, definition in columns_to_add.items():
                if column not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
