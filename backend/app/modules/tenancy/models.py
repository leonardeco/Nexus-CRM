from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.engine import Base


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = {"schema": "catalog"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    schema_name: Mapped[str] = mapped_column(String(34), unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(
        String(32), nullable=False, default="starter", server_default="starter"
    )
    seat_cap: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, server_default="2"
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
