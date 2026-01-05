from sqlalchemy import (
    Column,
    Integer,
    Date,
    String,
    ForeignKey
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class OfficeHoliday(Base):
    __tablename__ = "office_holidays"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        nullable=False
    )

    holiday_date = Column(Date, nullable=False)
    description = Column(String(255))

    # office = relationship("Office", backref="holidays")
    office = relationship(
        "Office",
        back_populates="holidays"
    )    

