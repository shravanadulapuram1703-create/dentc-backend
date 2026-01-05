from sqlalchemy import Column, Integer, Numeric, String, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base



class UserTimeClock(Base):
    __tablename__ = "user_time_clock_settings"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("public.users.id", ondelete="CASCADE"), unique=True)

    pay_rate = Column(Numeric(10, 2))
    overtime_method = Column(String(20))  # daily / weekly
    overtime_rate = Column(Numeric(10, 2))

    user = relationship("User", back_populates="time_clock")
