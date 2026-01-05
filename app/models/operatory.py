from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class Operatory(Base):
    __tablename__ = "operatories"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        nullable=False
    )

    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)

    # office = relationship("Office", backref="operatories")
    office = relationship(
        "Office",
        back_populates="operatories"
    )    
