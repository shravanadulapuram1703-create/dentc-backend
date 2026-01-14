from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Time,
    ForeignKey, Text, TIMESTAMP, Identity,Numeric
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

from sqlalchemy.dialects.postgresql import JSONB

from app.api.v1.offices.schemas import OfficeAdvancedPayload



# ==================================================
# OFFICE
# ==================================================

class Office(Base):
    __tablename__ = "offices"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)

    tenant_id = Column(
        Integer,
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=False
    )

    office_name = Column(String)
    office_code = Column(String, nullable=False, unique=True)

    timezone = Column(String)
    address_line1 = Column(String)
    address_line2 = Column(String)
    city = Column(String)
    state = Column(String)
    zip = Column(String)

    phone1 = Column(String)
    phone2 = Column(String)
    phone1ext = Column(String)
    email = Column(String)

    is_active = Column(Boolean, default=True)

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now()
    )


    # Relationships

    roles = relationship("OfficeRole", back_populates="office")
    statements = relationship("OfficeStatement", back_populates="office", uselist=False, cascade="all, delete-orphan")


    schedules = relationship("OfficeSchedule",back_populates="office",cascade="all, delete-orphan",lazy="select")


    holidays = relationship(
        "OfficeHoliday",
        back_populates="office",
        cascade="all, delete-orphan"
    )


    operatories = relationship("OfficeOperatory",back_populates="office",cascade="all, delete-orphan")

    tenant = relationship("Tenant", back_populates="office")

    users = relationship("UserOffice",back_populates="office",cascade="all, delete-orphan")

    other_info = relationship(
        "OfficeOtherInfo",
        uselist=False,
        back_populates="office",
        cascade="all, delete-orphan"
        )

    # integarations = relationship("OfficeIntegrations", uselist=False,back_populates="office",cascade="all, delete-orphan")

    # smart_assist = relationship("OfficeSmartAssist", back_populates = "office",uselist=False,cascade="all, delete-orphan")
    
    smart_assist = relationship(
        "OfficeSmartAssist",
        back_populates="office",
        uselist=False,
        cascade="all, delete-orphan"
    )

    integrations = relationship(
        "OfficeIntegrations",
        uselist=False,
        back_populates="office",
        cascade="all, delete-orphan"
    )

    imaging_systems = relationship(
        "OfficeImagingSystem",
        back_populates="office",
        cascade="all, delete-orphan"
    )

    patient_urls = relationship(
        "OfficePatientUrls",
        uselist=False,
        back_populates="office",
        cascade="all, delete-orphan"
    )

    payment_methods = relationship(
        "OfficePaymentMethod",
        back_populates="office",
        cascade="all, delete-orphan"
    )

    transworld = relationship(
        "OfficeTransworld",
        uselist=False,
        back_populates="office",
        cascade="all, delete-orphan"
    )


    # in Office model

    advanced = relationship(
                    "OfficeAdvancedSettings",
                    uselist=False,
                    back_populates="office",
                    cascade="all, delete-orphan"
                )


    
    def __repr__(self):
        return f"<Office id={self.id} code={self.office_code}>"


# ==================================================
# OFFICE STATEMENTS
# ==================================================

class OfficeStatement(Base):
    __tablename__ = "office_statements"
    __table_args__ = {"schema": "public"}

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        primary_key=True
    )

    general_message = Column(Text)
    current_message = Column(Text)
    msg_30_day = Column(Text)
    msg_60_day = Column(Text)
    msg_90_day = Column(Text)
    msg_120_day = Column(Text)
    correspondence_name = Column(Text)
    statement_address = Column(Text)
    statement_name = Column(Text)
    statement_phone = Column(Text)
    logo_url = Column(Text)
    statement_city = Column(Text)
    statement_state = Column(Text)
    statement_zip = Column(Text)

    office = relationship("Office", back_populates="statements")


# ==================================================
# OFFICE SCHEDULES
# ==================================================

class OfficeSchedule(Base):
    __tablename__ = "office_schedules"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        nullable=False
    )

    day_of_week = Column(String(50))
    start_time = Column(Time)
    end_time = Column(Time)
    lunch_start = Column(Time)
    lunch_end = Column(Time)
    is_closed = Column(Boolean, default=False)

    office = relationship("Office", back_populates="schedules")

    

# ==================================================
# OFFICE HOLIDAYS
# ==================================================

class OfficeHoliday(Base):
    __tablename__ = "office_holidays"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        nullable=False
    )
    from_date = Column(Date)
    to_date = Column(Date)

    name = Column(String)
    description = Column(String)

    is_active = Column(Boolean, default=True)


    office = relationship("Office", back_populates="holidays")


# ==================================================
# OFFICE OPERATORIES
# ==================================================

class OfficeOperatory(Base):
    __tablename__ = "office_operatories"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        nullable=False
    )

    name = Column(String, nullable=False)
    display_order = Column(Integer)
    is_active = Column(Boolean, default=True)
    has_future_appointments = Column(Boolean, default=False)

    office = relationship("Office", back_populates="operatories")



class OfficeOtherInfo(Base):
    __tablename__ = "office_other_info"
    __table_args__ = {"schema": "public"}

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        primary_key=True
    )

    tax_id = Column(String(50))
    insurance_billing_provider = Column(String(255))
    insurance_billing_providerid = Column(String(255))
    billing_license_type = Column(String(100))
    opening_date = Column(Date)
    office_group = Column(String(100))
    default_ucr_fee_schedule = Column(String(100))
    default_fee_schedule = Column(String(100))
    scheduler_interval_minutes = Column(Integer, default=10)

    office = relationship("Office", back_populates="other_info")


class OfficeIntegrations(Base):
    __tablename__ = "office_integrations"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    office_id = Column(Integer, ForeignKey("public.offices.id"), nullable=False)

    eclaim_type = Column(String(50))
    edi_username = Column(String(100))
    edi_password = Column(Text)

    # imaging_system_1 = Column(String(100))
    # imaging_system_2 = Column(String(100))
    # imaging_system_3 = Column(String(100))

    # imaging_mode_1 = Column(String(50))
    # imaging_mode_2 = Column(String(50))
    # imaging_mode_3 = Column(String(50))

    text_phone = Column(String(20))
    text_verified = Column(Boolean, default=False)

    created_at = Column(TIMESTAMP, server_default=func.now())

    office = relationship("Office", back_populates="integrations")

    


class OfficeImagingSystem(Base):
    __tablename__ = "office_imaging_systems"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    office_id = Column(Integer, ForeignKey("public.offices.id"), nullable=False)

    system_name = Column(String(100))
    link_type = Column(String(50))
    mode = Column(String(50))
    display_order = Column(Integer)

    office = relationship("Office", back_populates="imaging_systems")

    

    


class OfficePatientUrls(Base):
    __tablename__ = "office_patient_urls"
    __table_args__ = {"schema": "public"}

    office_id = Column(Integer, ForeignKey("public.offices.id"), primary_key=True)

    forms_url = Column(Text)
    scheduling_url = Column(Text)
    financing_url = Column(Text)
    custom_url_1 = Column(Text)
    custom_url_2 = Column(Text)

    office = relationship("Office", back_populates="patient_urls")

    




class OfficePaymentMethod(Base):
    __tablename__ = "office_payment_methods"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    office_id = Column(Integer, ForeignKey("public.offices.id"))
    card_type = Column(String(50))
    is_active = Column(Boolean, default=True)

    office = relationship("Office", back_populates="payment_methods")






# class OfficeIntegration(Base):
#     __tablename__ = "office_integrations"
#     __table_args__ = {"schema": "public"}
#     id = Column(Integer)#, primary_key=True)

#     office_id = Column(
#         Integer,
#         ForeignKey("public.offices.id", ondelete="CASCADE"),
#         primary_key=True
#     )

#     eclaim_type = Column(String(50))
#     edi_username = Column(String(100))
#     edi_password = Column(Text)
#     imaging_system_1 = Column(String(100))
#     imaging_system_2 = Column(String(100))
#     imaging_system_3 = Column(String(100))
#     text_phone = Column(String(20))
#     transactional_email = Column(String(255))
#     created_at = Column(TIMESTAMP)
#     imaging_mode_1 = Column(String(50))
#     imaging_mode_2 = Column(String(50))
#     imaging_mode_3 = Column(String(50))
#     text_verified = Column(Boolean)

#     office = relationship("Office", back_populates="integarations")


# app/models/offices.py

# class OfficeSmartAssist(Base):
#     __tablename__ = "office_smart_assist"
#     __table_args__ = {"schema": "public"}

#     id = Column(Integer, primary_key=True) ##
#     office_id = Column(Integer, ForeignKey("public.offices.id", ondelete="CASCADE"), nullable=False, unique=True)

#     enabled = Column(Boolean, default=False, nullable=False)

#     office = relationship("Office", back_populates = "smart_assist")

#     items = relationship(
#         "OfficeSmartAssistItem",
#         back_populates="smart_assist_item",
#         cascade="all, delete-orphan"
#     )
# 

class OfficeSmartAssist(Base):
    __tablename__ = "office_smart_assist"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, 
                Identity(always=True),
                primary_key=True)

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    enabled = Column(Boolean, default=False, nullable=False)

    #  STORE UI PAYLOAD DIRECTLY
    items = Column(JSONB, nullable=False, default=dict)

    office = relationship(
        "Office",
        back_populates="smart_assist",
        uselist=False,
    )




# class OfficeSmartAssistItem(Base):
#     __tablename__ = "office_smart_assist_items"
#     __table_args__ = {"schema": "public"}

#     id = Column(Integer, primary_key=True)
#     smart_assist_id = Column(
#         Integer,
#         ForeignKey("public.office_smart_assist.id", ondelete="CASCADE")
#     )

#     key = Column(String(50), nullable=False)  # payment, hipaa, consentForm1
#     frequency = Column(String(50), nullable=True)
#     enabled = Column(Boolean, default=False)
#     include_balance = Column(Boolean, default=False)
#     template = Column(String(255), nullable=True)

#     # smart_assist_item = relationship("OfficeSmartAssist", back_populates="items")
#     smart_assist = relationship(
#         "OfficeSmartAssist",
#         back_populates="office",
#         uselist=False,
#         cascade="all, delete-orphan"
#     )


# ==================================================
# OFFICE TRANSWORLD
# ==================================================

class OfficeTransworld(Base):
    __tablename__ = "office_transworld"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )

    accelerator_account = Column(String(100))
    collections_account = Column(String(100))
    user_id = Column(String(100))
    password = Column(Text)
    aging_days = Column(Integer)

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now()
    )

    office = relationship(
        "Office",
        back_populates="transworld",
        uselist=False
    )



class OfficeAdvancedSettings(Base):
    __tablename__ = "office_advanced_settings"
    __table_args__ = {"schema": "public"}

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        primary_key=True
    )

    # FINANCIAL
    annual_finance_charge_percent = Column(Numeric(5, 2))
    minimum_balance = Column(Numeric(10, 2))
    minimum_finance_charge = Column(Numeric(10, 2))
    days_before_finance_charge = Column(Integer)
    sales_tax_percent = Column(Numeric(5, 2))

    # INSURANCE / SCHEDULER
    insurance_group = Column(String(255))
    scheduler_end_date = Column(Date)
    eligibility_threshold_days = Column(Integer)
    send_ecard = Column(Boolean, default=False)

    # DEFAULTS
    default_place_of_service = Column(String(50))
    default_appointment_duration = Column(Integer)
    default_area_code = Column(String(3))
    default_city = Column(String(100))
    default_state = Column(String(2))
    default_zip = Column(String(10))
    preferred_provider = Column(String(255))
    default_coverage_type = Column(String(50))
    is_ortho_office = Column(Boolean, default=False)

    # PATIENT CHECK-IN
    hipaa_notice = Column(Boolean, default=False)
    consent_form = Column(Boolean, default=False)
    additional_consent_form = Column(Boolean, default=False)

    # AUTOMATION
    automated_campaigns_effective_date = Column(Date)

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now()
    )

    office = relationship("Office", back_populates="advanced")