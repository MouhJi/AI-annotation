from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base

class ProjectClassMapping(Base):
    __tablename__ = "project_class_mappings"
    __table_args__ = (UniqueConstraint("project_id", "model_class_id", name="uq_project_model_class"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    model_class_id: Mapped[int] = mapped_column(Integer)
    model_class_name: Mapped[str] = mapped_column(String(120))
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    label_class = relationship("LabelClass")

class AutoLabelPrediction(Base):
    __tablename__ = "auto_label_predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id"), index=True)
    model_class_id: Mapped[int] = mapped_column(Integer)
    model_class_name: Mapped[str] = mapped_column(String(120))
    mapped_class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id"), nullable=True)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)
    prediction_type: Mapped[str] = mapped_column(String(16), default="bbox")
    points_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    human_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    annotation_id: Mapped[int | None] = mapped_column(ForeignKey("annotations.id"), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    image = relationship("Image")
    mapped_class = relationship("LabelClass", foreign_keys=[mapped_class_id])
    annotation = relationship("Annotation")
