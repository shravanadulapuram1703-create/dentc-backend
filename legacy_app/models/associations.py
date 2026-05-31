from sqlalchemy import Table, Column, Integer, ForeignKey
# from app.db.base import Base
from app.core.database import Base 
from sqlalchemy import Table, Column, Integer, Boolean, ForeignKey
from app.core.database import Base

# -----------------------------
# USER ↔ ROLE ↔ OFFICE
# # -----------------------------
# user_roles_ = Table(
#     "user_roles",
#     Base.metadata,
#     Column(
#         "user_id",
#         Integer,
#         ForeignKey("public.users.id", ondelete="CASCADE"),
#         primary_key=True,
#     ),
#     Column(
#         "role_id",
#         Integer,
#         ForeignKey("public.roles.id", ondelete="CASCADE"),
#         primary_key=True,
#     ),
#     Column(
#         "office_id",
#         Integer,
#         nullable=False,
#         primary_key=True,
#     ),
#     schema="public",
# )

# -----------------------------
# ROLE ↔ PERMISSION
# -----------------------------
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        Integer,
        ForeignKey("public.roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        Integer,
        ForeignKey("public.permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    schema="public",
)

# -----------------------------
# USER ↔ PERMISSION (OVERRIDES)
# -----------------------------
user_permissions = Table(
    "user_permissions",
    Base.metadata,
    Column(
        "user_id",
        Integer,
        ForeignKey("public.users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        Integer,
        ForeignKey("public.permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "allowed",
        Boolean,
        default=True,
        nullable=False,
    ),
    schema="public",
)
