from sqlalchemy import (
    Column,
    Integer,
    Time,
    ForeignKey,
    UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class OfficeSchedule(Base):
    __tablename__ = "office_schedules"
    __table_args__ = (
        UniqueConstraint("office_id", "day_of_week"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True)

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        nullable=False
    )

    day_of_week = Column(Integer, nullable=False)
    # 1=Monday ... 7=Sunday
    start_time = Column(Time)
    end_time = Column(Time)

    day_start = Column(Time)
    day_end = Column(Time)

    lunch_start = Column(Time)
    lunch_end = Column(Time)

    # office = relationship("Office", backref="schedules")
    office = relationship(
        "Office",
        back_populates="schedules"
    )   
