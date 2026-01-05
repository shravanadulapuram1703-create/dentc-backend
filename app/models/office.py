from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    TIMESTAMP,
    func
)

class Office(Base):
    __tablename__ = "offices"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        Integer,
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=False
    )

    office_code = Column(String(20), unique=True, nullable=False)  # ROBIN
    office_name = Column(String(255), nullable=False)

    address_line1 = Column(String(255))
    city = Column(String(100))
    state = Column(String(50))
    zip = Column(String(20))

    timezone = Column(String(50))

    phone1 = Column(String(20))
    phone2 = Column(String(20))
    fax = Column(String(20))
    email = Column(String(255))

    is_active = Column(Boolean, default=True)

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="offices")
    users = relationship("UserOffice", back_populates="office", cascade="all, delete")
    roles = relationship("OfficeRole", back_populates="office", cascade="all, delete")
    statement = relationship("OfficeStatement", uselist=False)
    integrations = relationship("OfficeIntegration")
    schedules = relationship("OfficeSchedule")
    holidays = relationship("OfficeHoliday")
    operatories = relationship("Operatory")

    statements = relationship(
        "OfficeStatement",
        back_populates="office",
        cascade="all, delete-orphan"
    )

