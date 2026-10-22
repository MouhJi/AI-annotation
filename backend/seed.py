from app.database import SessionLocal
from app.models import Project, LabelClass
# Run `alembic upgrade head` first. Seeded projects remain unclaimed until an operator assigns an owner.
db=SessionLocal()
if not db.query(Project).filter_by(name="Traffic Detection").first():
    project=Project(name="Traffic Detection",description="Traffic object detection dataset")
    db.add(project); db.flush()
    db.add_all([LabelClass(project_id=project.id,name=name) for name in ["car","motorbike","bus","truck"]]); db.commit()
    print("Seeded Traffic Detection")
else: print("Seed data already exists")
db.close()
