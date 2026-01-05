from sqlalchemy import Column, Integer, String
from app.core.database import Base


class OfficePermission(Base):
    __tablename__ = "office_permissions"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    code = Column(String(100), unique=True, nullable=False)
    description = Column(String(255))
    module = Column(String(50))  # SCHEDULE, STATEMENT, SMARTASSIST
    action = Column(String(50))  # VIEW, EDIT, DELETE, CREATE