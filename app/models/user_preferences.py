from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # UI / Navigation
    startup_screen = Column(String(50), nullable=True)
    toolbar = Column(Boolean, default=True)

    # Perio
    perio_template = Column(String(50), nullable=True)
    default_perio_screen = Column(String(50), nullable=True)

    # Search / Navigation
    default_navigation_search = Column(Boolean, default=True)
    default_search_by = Column(String(50), nullable=True)

    # Production / View
    production_view = Column(String(50), nullable=True)
    hide_provider_time = Column(Boolean, default=False)
    show_production_colors = Column(Boolean, default=True)

    # Printing / Entry
    print_labels = Column(Boolean, default=False)
    prompt_entry_date = Column(Boolean, default=True)

    # Patient filtering
    include_inactive_patients = Column(Boolean, default=False)
    referral_view = Column(String(50), nullable=True)

    # User role type (UI behavior)
    user_role_type = Column(String(50), nullable=True)

    # Optional relationship (not required)
    user = relationship("User", back_populates="preferences")#, lazy="joined")

    user_id = Column(
    Integer,
    ForeignKey("public.users.id", ondelete="CASCADE"),
    nullable=False,
    unique=True,
)

