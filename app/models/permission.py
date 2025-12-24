from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.associations import role_permissions


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    code = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    module = Column(String(50))

    roles = relationship(
        "Role",
        secondary=role_permissions,
        back_populates="permissions",
    )
