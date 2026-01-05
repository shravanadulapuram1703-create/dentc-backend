from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    ForeignKey
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class OfficeStatement(Base):
    __tablename__ = "office_statements"
    __table_args__ = {"schema": "public"}

    # id = Column(Integer, primary_key=True)

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        primary_key=True
    )

    # Monthly statement messages
    general_message = Column(Text)
    current_message = Column(Text)
    msg_30_day = Column(Text)
    msg_60_day = Column(Text)
    msg_90_day = Column(Text)
    msg_120_day = Column(Text)

    # Statement settings
    correspondence_name = Column(String(255))
    statement_address = Column(String(255))
    statement_city_state_zip = Column(String(255))
    statement_phone = Column(String(20))
    logo_url = Column(Text)

    # office = relationship("Office", backref="statement")
    office = relationship(
        "Office",
        back_populates="statements"
    )    
