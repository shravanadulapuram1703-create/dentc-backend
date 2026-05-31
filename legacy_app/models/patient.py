from sqlalchemy import Column, Integer, String, Date, TIMESTAMP, Boolean, Text, ForeignKey, DECIMAL, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base



class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    chart_no = Column(String(50), unique=True, nullable=True, index=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    preferred_name = Column(String(100), nullable=True)
    dob = Column(Date, nullable=True)
    gender = Column(String(10), nullable=True)  # M, F, O, or other
    title = Column(String(10), nullable=True)
    pronouns = Column(String(20), nullable=True)
    marital_status = Column(String(50), nullable=True)
    ssn = Column(String(20), nullable=True, index=True)
    medicaid_id = Column(String(50), nullable=True, index=True)
    
    # Contact info (legacy - kept for backward compatibility)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    
    # Office and provider info
    home_office_id = Column(Integer, ForeignKey("public.offices.id"), nullable=True, index=True)
    preferred_provider_id = Column(String(50), nullable=True)
    preferred_hygienist_id = Column(String(50), nullable=True)
    fee_schedule_id = Column(String(50), nullable=True)
    
    # Patient type and flags
    patient_type = Column(String(20), default='General', index=True)
    is_active = Column(Boolean, default=True, index=True)
    is_ortho = Column(Boolean, default=False)
    is_child = Column(Boolean, default=False)
    is_collection_problem = Column(Boolean, default=False)
    is_employee_family = Column(Boolean, default=False)
    is_short_notice = Column(Boolean, default=False)
    is_senior = Column(Boolean, default=False)
    is_spanish_speaking = Column(Boolean, default=False)
    assign_benefits = Column(Boolean, default=True)
    hipaa_agreement = Column(Boolean, default=False)
    no_correspondence = Column(Boolean, default=False)
    no_auto_email = Column(Boolean, default=False)
    no_auto_sms = Column(Boolean, default=False)
    add_to_quickfill = Column(Boolean, default=False)
    
    # Preferences
    preferred_language = Column(String(50), default='English')
    preferred_contact = Column(String(50), nullable=True)
    
    # Referral info
    referral_type = Column(String(50), nullable=True)
    referred_by = Column(String(255), nullable=True)
    referred_to = Column(String(255), nullable=True)
    referral_to_date = Column(Date, nullable=True)
    
    # Guardian info
    guardian_name = Column(String(255), nullable=True)
    guardian_phone = Column(String(20), nullable=True)
    
    # Notes
    patient_notes = Column(Text, nullable=True)
    hipaa_sharing = Column(String(50), default='Full sharing allowed')
    
    # Timestamps
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
    updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())

    # AUDIT FIELDS (NEW)
    created_by = Column(String(64), nullable=False, index=True)
    updated_by = Column(String(64), nullable=True, index=True)
    
    # Relationships
    address = relationship("PatientAddress", back_populates="patient", uselist=False, cascade="all, delete-orphan")
    contact_info = relationship("PatientContactInfo", back_populates="patient", uselist=False, cascade="all, delete-orphan")
    responsible_party = relationship("ResponsibleParty", back_populates="patient_rel", uselist=False, cascade="all, delete-orphan")
    insurance_records = relationship("PatientInsurance", back_populates="patient", cascade="all, delete-orphan")
    account_members = relationship("PatientAccountMember", foreign_keys="PatientAccountMember.account_patient_id", back_populates="account_patient", cascade="all, delete-orphan")
    balance = relationship("PatientBalance", back_populates="patient", uselist=False, cascade="all, delete-orphan")
    clinical_info = relationship("PatientClinicalInfo", back_populates="patient", uselist=False, cascade="all, delete-orphan")
    medical_alerts = relationship("PatientMedicalAlert", back_populates="patient", cascade="all, delete-orphan")
    home_office = relationship("Office", foreign_keys=[home_office_id])


# class PatientAddress(Base):
#     __tablename__ = "patient_addresses"
#     __table_args__ = {"schema": "tenant_1"}

#     id = Column(Integer, primary_key=True, index=True)
#     patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)
#     address_line_1 = Column(String(255), nullable=True)
#     address_line_2 = Column(String(255), nullable=True)
#     city = Column(String(100), nullable=True)
#     state = Column(String(50), nullable=True)
#     zip = Column(String(20), nullable=True)
#     country = Column(String(50), default='USA')
#     address_type = Column(String(20), default='Home')
#     is_primary = Column(Boolean, default=True)
#     created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
#     updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())
    
#     patient = relationship("Patient", back_populates="address")
    
#     __table_args__ = (
#         UniqueConstraint('patient_id', 'address_type', name='uq_patient_address_type'),
#         {"schema": "tenant_1"}
#     )


class PatientAddress(Base):
    __tablename__ = "patient_addresses"
    __table_args__ = (
        UniqueConstraint('patient_id', 'address_type', name='uq_patient_address_type'),
        {"schema": "tenant_1"}
    )

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)
    address_line_1 = Column(String(255), nullable=True)
    address_line_2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    zip = Column(String(20), nullable=True)
    country = Column(String(50), default='USA')
    address_type = Column(String(20), default='Home')
    is_primary = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
    updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())
    
    patient = relationship("Patient", back_populates="address")


# class PatientContactInfo(Base):
#     __tablename__ = "patient_contact_info"
#     __table_args__ = {"schema": "tenant_1"}

#     id = Column(Integer, primary_key=True, index=True)
#     patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
#     home_phone = Column(String(20), nullable=True, index=True)
#     cell_phone = Column(String(20), nullable=True, index=True)
#     work_phone = Column(String(20), nullable=True, index=True)
#     email = Column(String(255), nullable=True, index=True)
#     preferred_contact = Column(String(50), nullable=True)
#     created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
#     updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())
    
#     patient = relationship("Patient", back_populates="contact_info")




class PatientContactInfo(Base):
    __tablename__ = "patient_contact_info"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    home_phone = Column(String(20), nullable=True, index=True)
    cell_phone = Column(String(20), nullable=True, index=True)
    work_phone = Column(String(20), nullable=True, index=True)
    email = Column(String(255), nullable=True, index=True)
    preferred_contact = Column(String(50), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
    updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())
    
    patient = relationship("Patient", back_populates="contact_info")



class ResponsibleParty(Base):
    __tablename__ = "responsible_parties"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    responsible_party_id = Column(String(50), nullable=True)  # Reference to another patient if self
    name = Column(String(255), nullable=False, index=True)
    type = Column(String(50), nullable=True)  # Cash, Insurance, etc.
    relationship_type = Column("_relationship", String(50), nullable=True)  # Self, Spouse, Parent, etc. (DB column name is 'relationship')
    phone = Column(String(20), nullable=True, index=True)
    email = Column(String(255), nullable=True, index=True)
    home_office_id = Column(Integer, ForeignKey("public.offices.id"), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
    updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())
    
    patient_rel = relationship("Patient", back_populates="responsible_party")  # Renamed to avoid conflict with Column name
    home_office = relationship("Office", foreign_keys=[home_office_id])



# class ResponsibleParty(Base):
#     __tablename__ = "responsible_parties"
#     __table_args__ = {"schema": "tenant_1"}

#     id = Column(Integer, primary_key=True, index=True)
#     patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
#     responsible_party_id = Column(String(50), nullable=True)
#     name = Column(String(255), nullable=False, index=True)
#     type = Column(String(50), nullable=True)
#     _relationship = Column(String(50), nullable=True)
#     phone = Column(String(20), nullable=True, index=True)
#     email = Column(String(255), nullable=True, index=True)
#     home_office_id = Column(Integer, ForeignKey("public.offices.id"), nullable=True)
#     created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
#     updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())
    
#     patient = relationship("Patient", back_populates="responsible_party")
#     home_office = relationship("Office", foreign_keys=[home_office_id])


# class PatientInsurance(Base):
#     __tablename__ = "patient_insurance"
#     __table_args__ = {"schema": "tenant_1"}

#     id = Column(Integer, primary_key=True, index=True)
#     patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)
#     insurance_type = Column(String(20), nullable=False)  # primary_dental, secondary_dental, primary_medical, secondary_medical
#     carrier_name = Column(String(255), nullable=True)
#     plan_name = Column(String(255), nullable=True)
#     group_number = Column(String(100), nullable=True)
#     subscriber_id = Column(String(100), nullable=True, index=True)
#     subscriber_name = Column(String(255), nullable=True)
#     relationship_type = Column("_relationship", String(50), nullable=True)  # Self, Spouse, Child, etc. (DB column name is 'relationship')
#     carrier_phone = Column(String(20), nullable=True)
#     individual_max_remaining = Column(DECIMAL(10, 2), nullable=True)
#     individual_deductible_remaining = Column(DECIMAL(10, 2), nullable=True)
#     is_active = Column(Boolean, default=True)
#     created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
#     updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())
    
#     patient = relationship("Patient", back_populates="insurance_records")
    
#     __table_args__ = (
#         UniqueConstraint('patient_id', 'insurance_type', name='uq_patient_insurance_type'),
#         {"schema": "tenant_1"}
#     )




class PatientInsurance(Base):
    __tablename__ = "patient_insurance"
    __table_args__ = (
        UniqueConstraint('patient_id', 'insurance_type', name='uq_patient_insurance_type'),
        {"schema": "tenant_1"}
    )

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)
    insurance_type = Column(String(20), nullable=False)
    carrier_name = Column(String(255), nullable=True)
    plan_name = Column(String(255), nullable=True)
    group_number = Column(String(100), nullable=True)
    subscriber_id = Column(String(100), nullable=True, index=True)
    subscriber_name = Column(String(255), nullable=True)
    _relationship = Column(String(50), nullable=True)
    carrier_phone = Column(String(20), nullable=True)
    individual_max_remaining = Column(DECIMAL(10, 2), nullable=True)
    individual_deductible_remaining = Column(DECIMAL(10, 2), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
    updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())
    
    patient = relationship("Patient", back_populates="insurance_records")



# class FeeSchedule(Base):
#     __tablename__ = "fee_schedules"
#     __table_args__ = {"schema": "tenant_1"}

#     id = Column(Integer, primary_key=True, index=True)
#     fee_schedule_id = Column(String(50), unique=True, nullable=False, index=True)
#     fee_schedule_name = Column(String(255), nullable=False)
#     description = Column(Text, nullable=True)
#     office_id = Column(Integer, ForeignKey("public.offices.id"), nullable=True, index=True)
#     is_active = Column(Boolean, default=True)
#     created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
#     updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())
    
#     office = relationship("Office", foreign_keys=[office_id])



class FeeSchedule(Base):
    __tablename__ = "fee_schedules"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    fee_schedule_id = Column(String(50), unique=True, nullable=False, index=True)
    fee_schedule_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    office_id = Column(Integer, ForeignKey("public.offices.id"), nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
    updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())
    
    office = relationship("Office", foreign_keys=[office_id])


# class PatientType(Base):
#     __tablename__ = "patient_types"
#     __table_args__ = {"schema": "tenant_1"}

#     id = Column(Integer, primary_key=True, index=True)
#     code = Column(String(20), unique=True, nullable=False)
#     name = Column(String(100), nullable=False)
#     description = Column(Text, nullable=True)
#     is_active = Column(Boolean, default=True)
#     created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)




class PatientType(Base):
    __tablename__ = "patient_types"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)



# class ReferralType(Base):
#     __tablename__ = "referral_types"
#     __table_args__ = {"schema": "tenant_1"}

#     id = Column(Integer, primary_key=True, index=True)
#     code = Column(String(20), unique=True, nullable=False)
#     name = Column(String(100), nullable=False)
#     description = Column(Text, nullable=True)
#     is_active = Column(Boolean, default=True)
#     created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)



class ReferralType(Base):
    __tablename__ = "referral_types"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)



# class ResponsiblePartyRelationship(Base):
#     __tablename__ = "responsible_party_relationships"
#     __table_args__ = {"schema": "tenant_1"}

#     id = Column(Integer, primary_key=True, index=True)
#     code = Column(String(20), unique=True, nullable=False)
#     name = Column(String(100), nullable=False)
#     description = Column(Text, nullable=True)
#     is_active = Column(Boolean, default=True)
#     created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)




class ResponsiblePartyRelationship(Base):
    __tablename__ = "responsible_party_relationships"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)



# class ContactPreference(Base):
#     __tablename__ = "contact_preferences"
#     __table_args__ = {"schema": "tenant_1"}

#     id = Column(Integer, primary_key=True, index=True)
#     code = Column(String(20), unique=True, nullable=False)
#     name = Column(String(100), nullable=False)
#     description = Column(Text, nullable=True)
#     is_active = Column(Boolean, default=True)
#     created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)




class ContactPreference(Base):
    __tablename__ = "contact_preferences"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)



# class PatientAccountMember(Base):
#     __tablename__ = "patient_account_members"
#     __table_args__ = {"schema": "tenant_1"}

#     id = Column(Integer, primary_key=True, index=True)
#     account_patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)
#     member_patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)
#     relationship_type = Column("_relationship", String(50), nullable=True)  # DB column name is 'relationship'
#     created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
    
#     account_patient = relationship("Patient", foreign_keys=[account_patient_id], back_populates="account_members")
#     member_patient = relationship("Patient", foreign_keys=[member_patient_id])
    
#     __table_args__ = (
#         UniqueConstraint('account_patient_id', 'member_patient_id', name='uq_account_member'),
#         {"schema": "tenant_1"}
#     )




class PatientAccountMember(Base):
    __tablename__ = "patient_account_members"
    __table_args__ = (
        UniqueConstraint('account_patient_id', 'member_patient_id', name='uq_account_member'),
        {"schema": "tenant_1"}
    )

    id = Column(Integer, primary_key=True, index=True)
    account_patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)
    member_patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)
    _relationship = Column(String(50), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
    
    account_patient = relationship("Patient", foreign_keys=[account_patient_id], back_populates="account_members")
    member_patient = relationship("Patient", foreign_keys=[member_patient_id])




# class PatientBalance(Base):
#     __tablename__ = "patient_balances"
#     __table_args__ = {"schema": "tenant_1"}

#     id = Column(Integer, primary_key=True, index=True)
#     patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
#     account_balance = Column(DECIMAL(10, 2), default=0.00)
#     current = Column(DECIMAL(10, 2), default=0.00)
#     over_30 = Column(DECIMAL(10, 2), default=0.00)
#     over_60 = Column(DECIMAL(10, 2), default=0.00)
#     over_90 = Column(DECIMAL(10, 2), default=0.00)
#     over_120 = Column(DECIMAL(10, 2), default=0.00)
#     last_insurance_payment = Column(DECIMAL(10, 2), nullable=True)
#     last_insurance_payment_date = Column(Date, nullable=True)
#     last_patient_payment = Column(DECIMAL(10, 2), nullable=True)
#     last_patient_payment_date = Column(Date, nullable=True)
#     updated_at = Column(TIMESTAMP, server_default=func.now(), nullable=True, onupdate=func.now())
    
#     patient = relationship("Patient", back_populates="balance")




class PatientBalance(Base):
    __tablename__ = "patient_balances"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    account_balance = Column(DECIMAL(10, 2), default=0.00)
    current = Column(DECIMAL(10, 2), default=0.00)
    over_30 = Column(DECIMAL(10, 2), default=0.00)
    over_60 = Column(DECIMAL(10, 2), default=0.00)
    over_90 = Column(DECIMAL(10, 2), default=0.00)
    over_120 = Column(DECIMAL(10, 2), default=0.00)
    last_insurance_payment = Column(DECIMAL(10, 2), nullable=True)
    last_insurance_payment_date = Column(Date, nullable=True)
    last_patient_payment = Column(DECIMAL(10, 2), nullable=True)
    last_patient_payment_date = Column(Date, nullable=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(), nullable=True, onupdate=func.now())
    
    patient = relationship("Patient", back_populates="balance")



# class PatientClinicalInfo(Base):
#     __tablename__ = "patient_clinical_info"
#     __table_args__ = {"schema": "tenant_1"}

#     id = Column(Integer, primary_key=True, index=True)
#     patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
#     first_visit = Column(Date, nullable=True)
#     last_visit = Column(Date, nullable=True)
#     next_visit = Column(Date, nullable=True)
#     next_recall = Column(Date, nullable=True)
#     last_pano_chart = Column(Date, nullable=True)
#     updated_at = Column(TIMESTAMP, server_default=func.now(), nullable=True, onupdate=func.now())
    
#     patient = relationship("Patient", back_populates="clinical_info")


class PatientClinicalInfo(Base):
    __tablename__ = "patient_clinical_info"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    first_visit = Column(Date, nullable=True)
    last_visit = Column(Date, nullable=True)
    next_visit = Column(Date, nullable=True)
    next_recall = Column(Date, nullable=True)
    last_pano_chart = Column(Date, nullable=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(), nullable=True, onupdate=func.now())
    
    patient = relationship("Patient", back_populates="clinical_info")


# class PatientMedicalAlert(Base):
#     __tablename__ = "patient_medical_alerts"
#     __table_args__ = {"schema": "tenant_1"}

#     id = Column(Integer, primary_key=True, index=True)
#     patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)
#     alert = Column(Text, nullable=False)
#     entered_by = Column(String(50), nullable=True)
#     created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
#     updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())
    
#     patient = relationship("Patient", back_populates="medical_alerts")


class PatientMedicalAlert(Base):
    __tablename__ = "patient_medical_alerts"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)
    alert = Column(Text, nullable=False)
    entered_by = Column(String(50), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
    updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())
    
    patient = relationship("Patient", back_populates="medical_alerts")


# ==================================================
# METADATA REFERENCE TABLES
# ==================================================

class Title(Base):
    __tablename__ = "titles"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)


class Pronoun(Base):
    __tablename__ = "pronouns"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)


class State(Base):
    __tablename__ = "states"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(2), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)


class MaritalStatus(Base):
    __tablename__ = "marital_statuses"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)


class Gender(Base):
    __tablename__ = "genders"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
