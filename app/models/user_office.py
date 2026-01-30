from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    DateTime
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from sqlalchemy.sql import func



# class UserOffice(Base):
#     __tablename__ = "user_offices"
#     __table_args__ = (
#         UniqueConstraint("user_id", "office_id"),
#         {"schema": "public"},
#     )

#     id = Column(Integer, primary_key=True)

#     user_id = Column(
#         Integer,
#         ForeignKey("public.users.id", ondelete="CASCADE"),
#         nullable=False
#     )

#     office_id = Column(
#         Integer,
#         ForeignKey("public.offices.id", ondelete="CASCADE"),
#         nullable=False
#     )

#     # is_primary = Column(Boolean, default=False)
#     # can_login = Column(Boolean, default=True)

#     role_id = Column(
#         Integer,
#         ForeignKey("public.office_roles.id"),
#         nullable=True
#     )

#     is_primary = Column(Boolean, default=False)
#     is_active = Column(Boolean, default=True)
#     created_at = Column(DateTime, server_default=func.now())

#     user = relationship("User", back_populates="offices")
#     offices = relationship(
#         "Office",
#         back_populates="users",
#         # cascade="all, delete-orphan"
#     )
#     role = relationship("OfficeRole")



# class UserOffice(Base):
#     __tablename__ = "user_offices"
#     __table_args__ = (
#         UniqueConstraint("user_id", "office_id"),
#         {"schema": "public"},
#     )

#     id = Column(Integer, primary_key=True)

#     user_id = Column(
#         Integer,
#         ForeignKey("public.users.id", ondelete="CASCADE"),
#         nullable=False
#     )

#     office_id = Column(
#         Integer,
#         ForeignKey("public.offices.id", ondelete="CASCADE"),
#         nullable=False
#     )

#     role_id = Column(
#         Integer,
#         ForeignKey("public.office_roles.id"),
#         nullable=True
#     )

#     is_primary = Column(Boolean, default=False)
#     is_active = Column(Boolean, default=True)
#     created_at = Column(DateTime, server_default=func.now())

#     #  CORRECT
#     user = relationship("User", back_populates="offices")
#     office = relationship("Office", back_populates="users")

#     role = relationship("OfficeRole")

class UserOffice(Base):
    __tablename__ = "user_offices"
    __table_args__ = (
        UniqueConstraint("user_id", "office_id"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False
    )

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        nullable=False
    )

    role_id = Column(
        Integer,
        ForeignKey("public.office_roles.id"),
        nullable=True
    )

    is_primary = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    #  CORRECT
    users = relationship("User", back_populates="office")

    office = relationship("Office", back_populates="users")

    #  DO NOT back_populates to Office
    role = relationship("OfficeRole")
