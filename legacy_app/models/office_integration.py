# from sqlalchemy import (
#     Column,
#     Integer,
#     String,
#     Text,
#     ForeignKey,
#     TIMESTAMP,
#     func
# )
# from sqlalchemy.orm import relationship
# from app.core.database import Base


# class OfficeIntegration(Base):
#     __tablename__ = "office_integrations"
#     __table_args__ = {"schema": "public"}

#     id = Column(Integer, primary_key=True)

#     office_id = Column(
#         Integer,
#         ForeignKey("public.offices.id", ondelete="CASCADE"),
#         nullable=False
#     )

#     # E-Claims
#     eclaim_type = Column(String(50))
#     edi_username = Column(String(100))
#     edi_password = Column(Text)

#     # Imaging systems
#     imaging_system_1 = Column(String(100))
#     imaging_system_2 = Column(String(100))
#     imaging_system_3 = Column(String(100))

#     imaging_mode_1 = Column(String(50))
#     imaging_mode_2 = Column(String(50))
#     imaging_mode_3 = Column(String(50))

#     # Messaging / email
#     text_phone = Column(String(20))
#     transactional_email = Column(String(255))

#     created_at = Column(TIMESTAMP, server_default=func.now())

#     # office = relationship("Office", backref="integrations")
#     office = relationship(
#         "Office",
#         back_populates="integrations"
#     )    

