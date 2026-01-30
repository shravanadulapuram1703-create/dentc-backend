# from sqlalchemy import Column, Integer, ForeignKey
# from app.core.database import Base
# from sqlalchemy.orm import relationship


# # class UserRole(Base):
# #     __tablename__ = "user_roles"
# #     __table_args__ = {"schema": "public"}
# #     id = Column(Integer, primary_key=True)

# #     user_id = Column(
# #         Integer,
# #         ForeignKey("public.users.id", ondelete="CASCADE"),
# #         primary_key=True,
# #     )

# #     role_id = Column(
# #         Integer,
# #         ForeignKey("public.roles.id", ondelete="CASCADE"),
# #         primary_key=True,
# #     )
# #     tenant_id = Column(
# #         Integer,
# #         ForeignKey("public.tenants.id", ondelete="CASCADE"),
# #         primary_key=True,
# #     )
# #     assigned_by = Column(
# #         Integer,
# #         ForeignKey("public.users.id", ondelete="SET NULL"),
# #         nullable=True,
# #     )

# #     # office_id = Column(
# #     #     Integer,
# #     #     primary_key=True,
# #     #     nullable=False,
# #     # )

# #     user = relationship("User", foreign_keys=[user_id], back_populates="user_roles")
# #     role = relationship("Role")


# # from sqlalchemy import Column, Integer, ForeignKey
# # from sqlalchemy.orm import relationship
# # # from app.db.base import Base


# class UserRole(Base):
#     __tablename__ = "user_roles"

#     id = Column(Integer, primary_key=True)

#     user_id = Column(Integer, ForeignKey("public.users.id"), nullable=False)
#     role_id = Column(Integer, ForeignKey("public.roles.id"), nullable=False)

#     tenant_id = Column(Integer, ForeignKey("public.tenants.id"), nullable=True)
#     # office_id = Column(Integer, ForeignKey("public.offices.id"), nullable=True)
#     assigned_by = Column(Integer, ForeignKey("public.users.id"), nullable=True)

#     #  THIS IS CRITICAL
#     user = relationship(
#         "User",
#         foreign_keys=[user_id],
#         back_populates="user_roles"
#     )

#     assigned_by_user = relationship(
#         "User",
#         foreign_keys=[assigned_by]
#     )

#     role = relationship("Role")


from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role_id = Column(
        Integer,
        ForeignKey("public.roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tenant_id = Column(
        Integer,
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    assigned_by = Column(
        Integer,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # -----------------------------
    # Relationships
    # -----------------------------

    # User who HAS the role
    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="user_roles",
    )

    # User who ASSIGNED the role
    assigned_by_user = relationship(
        "User",
        foreign_keys=[assigned_by],
    )

    # Role definition
    role = relationship(
        "Role",
        back_populates="user_roles",
    )

