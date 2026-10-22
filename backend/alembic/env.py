from alembic import context
from app.database import engine, Base
from app import models

if context.is_offline_mode():
    raise RuntimeError("This baseline inspects existing schemas; run migrations online against the intended database")
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction(): context.run_migrations()
