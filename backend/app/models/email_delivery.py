import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base
from .auth import utcnow


class EmailDeliveryAttempt(Base):
    """Operational receipt only: no body, token, credentials or recipient stored."""
    __tablename__ = "email_delivery_attempts"
    __table_args__ = (
        CheckConstraint("status IN ('prepared','sending','sent','development','failed')", name="ck_email_delivery_status"),
        Index("ix_email_delivery_resource", "purpose", "resource_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    purpose: Mapped[str] = mapped_column(String(30))
    resource_id: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="prepared")
    error_code: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
