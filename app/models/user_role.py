from sqlalchemy import Column, Integer, ForeignKey
from app.core.database import Base
from sqlalchemy.orm import relationship


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = {"schema": "public"}

    user_id = Column(
        Integer,
        ForeignKey("public.users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    role_id = Column(
        Integer,
        ForeignKey("public.roles.id", ondelete="CASCADE"),
        primary_key=True,
    )

    office_id = Column(
        Integer,
        primary_key=True,
        nullable=False,
    )
    
    user = relationship("User", back_populates="user_roles")
    role = relationship("Role")
