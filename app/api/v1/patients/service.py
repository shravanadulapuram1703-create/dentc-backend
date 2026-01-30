"""
Comprehensive Patient Service Layer
Implements all business logic for Patient Management API
"""
from sqlalchemy.orm import Session, joinedload, selectinload, contains_eager
from sqlalchemy import or_, and_, func as sql_func, case
from fastapi import HTTPException, status
from typing import Optional, List, Tuple
from datetime import datetime, date, timedelta
from decimal import Decimal
import re

from app.models.patient import (
    Patient, PatientAddress, PatientContactInfo, ResponsibleParty,
    PatientInsurance, FeeSchedule, PatientType, ReferralType,
    ResponsiblePartyRelationship, ContactPreference, PatientAccountMember,
    PatientBalance, PatientClinicalInfo, PatientMedicalAlert,
    Title, Pronoun, State, MaritalStatus, Gender
)
from app.models.offices import Office
from app.api.v1.patients.schemas import (
    PatientCreate, PatientUpdate, PatientResponse,
    PatientSearchResponse, PatientSearchListResponse,
    PatientDetailsResponse, PatientCreateRequest, PatientUpdateRequest,
    FeeSchedulesResponse, FeeScheduleMetadata,
    PatientTypesResponse, PatientTypeMetadata,
    ReferralTypesResponse, ReferralTypeMetadata,
    RelationshipsResponse, RelationshipMetadata,
    ContactPreferencesResponse, ContactPreferenceMetadata,
    TitlesResponse, TitleMetadata,
    PronounsResponse, PronounMetadata,
    StatesResponse, StateMetadata,
    MaritalStatusesResponse, MaritalStatusMetadata,
    GendersResponse, GenderMetadata,
    PatientMetadataResponse,
    DuplicateCheckRequest, DuplicateCheckResponse, DuplicateMatchSchema
)
from app.api.v1.scheduler.models import SchedulerAppointment

import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)

# Import cache utilities (with try/except for graceful degradation)
try:
    from app.core.cache import cache_result, CACHE_TTL, invalidate_cache
except ImportError:
    # Fallback if cache module is not available
    def cache_result(ttl=None, prefix=None):
        def decorator(func):
            return func
        return decorator
    CACHE_TTL = {"default": 300, "metadata": 3600, "patient_details": 300, "patient_search": 60, "fee_schedules": 1800}
    def invalidate_cache(pattern):
        pass


# ==================================================
# UTILITY FUNCTIONS
# ==================================================

def generate_chart_no(db: Session) -> str:
    """Generate a unique chart number for a new patient."""
    last_patient = (
        db.query(Patient)
        .filter(Patient.chart_no.isnot(None))
        .filter(Patient.chart_no.like('CH%'))
        .order_by(Patient.id.desc())
        .first()
    )
    
    if last_patient and last_patient.chart_no:
        try:
            last_num = int(last_patient.chart_no.replace('CH', ''))
            next_num = last_num + 1
        except ValueError:
            next_num = 1
    else:
        next_num = 1
    
    chart_no = f"CH{next_num:03d}"
    
    while db.query(Patient).filter(Patient.chart_no == chart_no).first():
        next_num += 1
        chart_no = f"CH{next_num:03d}"
    
    return chart_no


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """Normalize phone number by removing non-digit characters."""
    if not phone:
        return None
    return re.sub(r'\D', '', phone)


def calculate_age(dob: Optional[date]) -> Optional[int]:
    """Calculate age from date of birth."""
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# ==================================================
# PATIENT SEARCH SERVICE
# ==================================================

def search_patients(
    db: Session,
    search_by: str,
    search_value: str,
    search_for: str = "patient",
    patient_type: Optional[str] = None,
    search_scope: str = "all",
    include_inactive: bool = False,
    office_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0
) -> Tuple[List[PatientSearchResponse], int]:
    """
    Advanced patient search with field-specific criteria.
    
    Args:
        db: Database session
        search_by: Field to search in
        search_value: Search term
        search_for: "patient" or "responsible"
        patient_type: "general", "ortho", or None for both
        search_scope: "current", "all", or "group"
        include_inactive: Include inactive patients
        office_id: Office ID (required if search_scope is "current")
        limit: Maximum results
        offset: Pagination offset
    
    Returns:
        Tuple of (list of patients, total count)
    """
    # Validate search_by
    valid_search_fields = [
        "lastName", "firstName", "preferredName", "patientType",
        "medicaidId", "chartNumber", "ssn", "email", "birthDate",
        "homePhone", "cellPhone", "workPhone", "patientId",
        "responsiblePartyId", "responsiblePartyType", "subscriberId"
    ]
    
    if search_by not in valid_search_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid search_by field: {search_by}. Valid fields: {', '.join(valid_search_fields)}"
        )
    
    # Validate search_scope
    if search_scope == "current" and not office_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="office_id is required when search_scope is 'current'"
        )
    
    # Start building query
    if search_for == "responsible":
        # Search in responsible parties, then join to patients
        query = db.query(Patient).join(ResponsibleParty, Patient.id == ResponsibleParty.patient_id)
    else:
        query = db.query(Patient)
    
    # Apply search filter based on search_by field
    search_term = f"%{search_value}%"
    
    if search_by == "lastName":
        query = query.filter(Patient.last_name.ilike(search_term))
    elif search_by == "firstName":
        query = query.filter(Patient.first_name.ilike(search_term))
    elif search_by == "preferredName":
        query = query.filter(Patient.preferred_name.ilike(search_term))
    elif search_by == "patientType":
        query = query.filter(Patient.patient_type.ilike(search_term))
    elif search_by == "medicaidId":
        query = query.filter(Patient.medicaid_id.ilike(search_term))
    elif search_by == "chartNumber":
        query = query.filter(Patient.chart_no.ilike(search_term))
    elif search_by == "ssn":
        # SSN can be partial or full
        normalized_ssn = re.sub(r'\D', '', search_value)
        query = query.filter(Patient.ssn.ilike(f"%{normalized_ssn}%"))
    elif search_by == "email":
        if search_for == "responsible":
            query = query.filter(ResponsibleParty.email.ilike(search_term))
        else:
            # Use left join for contact_info
            query = query.outerjoin(PatientContactInfo).filter(
                or_(
                    Patient.email.ilike(search_term),
                    PatientContactInfo.email.ilike(search_term)
                )
            )
    elif search_by == "birthDate":
        # Parse date (supports YYYY-MM-DD or MM/DD/YYYY)
        try:
            if '/' in search_value:
                parts = search_value.split('/')
                if len(parts) == 3:
                    parsed_date = date(int(parts[2]), int(parts[0]), int(parts[1]))
                else:
                    raise ValueError("Invalid date format")
            else:
                parsed_date = date.fromisoformat(search_value)
            query = query.filter(Patient.dob == parsed_date)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date format. Use YYYY-MM-DD or MM/DD/YYYY"
            )
    elif search_by == "homePhone":
        normalized_phone = normalize_phone(search_value)
        if normalized_phone:
            query = query.outerjoin(PatientContactInfo).filter(
                PatientContactInfo.home_phone.ilike(f"%{normalized_phone}%")
            )
    elif search_by == "cellPhone":
        normalized_phone = normalize_phone(search_value)
        if normalized_phone:
            query = query.outerjoin(PatientContactInfo).filter(
                PatientContactInfo.cell_phone.ilike(f"%{normalized_phone}%")
            )
    elif search_by == "workPhone":
        normalized_phone = normalize_phone(search_value)
        if normalized_phone:
            query = query.outerjoin(PatientContactInfo).filter(
                PatientContactInfo.work_phone.ilike(f"%{normalized_phone}%")
            )
    elif search_by == "patientId":
        try:
            patient_id = int(search_value)
            query = query.filter(Patient.id == patient_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="patientId must be a valid integer"
            )
    elif search_by == "responsiblePartyId":
        query = query.join(ResponsibleParty).filter(
            ResponsibleParty.responsible_party_id.ilike(search_term)
        )
    elif search_by == "responsiblePartyType":
        query = query.join(ResponsibleParty).filter(
            ResponsibleParty.type.ilike(search_term)
        )
    elif search_by == "subscriberId":
        query = query.join(PatientInsurance).filter(
            PatientInsurance.subscriber_id.ilike(search_term)
        )
    
    # Apply filters
    if not include_inactive:
        query = query.filter(Patient.is_active == True)
    
    if patient_type:
        if patient_type.lower() == "general":
            query = query.filter(Patient.is_ortho == False)
        elif patient_type.lower() == "ortho":
            query = query.filter(Patient.is_ortho == True)
    
    if search_scope == "current" and office_id:
        query = query.filter(Patient.home_office_id == office_id)
    # "all" and "group" don't require additional filtering (user permissions handled at route level)
    
    # Get total count
    total = query.count()
    
    # Order and paginate
    query = query.order_by(Patient.last_name, Patient.first_name)
    query = query.limit(limit).offset(offset)
    
    # Eager load related data to prevent N+1 queries
    query = query.options(
        joinedload(Patient.home_office),
        selectinload(Patient.contact_info),
        selectinload(Patient.address)
    )
    
    # Execute and format results
    patients = query.all()
    
    results = []
    for patient in patients:
        # Get home office name (already loaded)
        home_office_name = None
        if patient.home_office_id and patient.home_office:
            home_office_name = patient.home_office.office_name
        
        # Get phone/email from contact_info if available (already loaded)
        phone = patient.phone or ""
        email = patient.email or ""
        if patient.contact_info:
            phone = phone or patient.contact_info.home_phone or patient.contact_info.cell_phone or patient.contact_info.work_phone or ""
            email = email or patient.contact_info.email or ""
        
        # Get address information (already loaded)
        address = ""
        city = ""
        state = ""
        zip_code = ""
        if patient.address:
            address = patient.address.address_line_1 or ""
            city = patient.address.city or ""
            state = patient.address.state or ""
            zip_code = patient.address.zip or ""
        
        # Format name
        first_name = patient.first_name or ""
        last_name = patient.last_name or ""
        full_name = f"{last_name}, {first_name}".strip(", ")
        
        # Format DOB
        dob_formatted = patient.dob.strftime("%m/%d/%Y") if patient.dob else ""
        
        # Format patient ID
        patient_id_formatted = patient.chart_no or f"PT-{str(patient.id).zfill(6)}"
        
        # Format chart number
        chart_number = patient.chart_no or f"CH-{patient.id}"
        
        # Get insurance info
        insurance = ""
        primary_insurance = db.query(PatientInsurance).filter(
            PatientInsurance.patient_id == patient.id,
            PatientInsurance.insurance_type == "primary_dental",
            PatientInsurance.is_active == True
        ).first()
        if primary_insurance:
            insurance = primary_insurance.carrier_name or ""
        
        # Get last visit and next appointment
        last_visit = ""
        next_appointment = ""
        if patient.clinical_info:
            if patient.clinical_info.last_visit:
                last_visit = patient.clinical_info.last_visit.strftime("%m/%d/%Y")
            if patient.clinical_info.next_visit:
                next_appointment = patient.clinical_info.next_visit.strftime("%m/%d/%Y")
        
        # Get balance
        balance_str = ""
        if patient.balance:
            balance_value = patient.balance.account_balance or Decimal("0.00")
            balance_str = f"${balance_value:.2f}"
        
        # Get emergency contact (from responsible party)
        emergency_contact = ""
        emergency_phone = ""
        if patient.responsible_party:
            emergency_contact = patient.responsible_party.name or ""
            emergency_phone = patient.responsible_party.phone or ""
        
        # Format office ID
        office_id_str = str(patient.home_office_id) if patient.home_office_id else ""
        
        results.append(PatientSearchResponse(
            id=patient.id,
            patientId=patient_id_formatted,
            name=full_name,
            firstName=first_name,
            lastName=last_name,
            dob=dob_formatted,
            phone=phone,
            email=email,
            address=address,
            city=city,
            state=state,
            zip=zip_code,
            insurance=insurance,
            lastVisit=last_visit,
            nextAppointment=next_appointment,
            balance=balance_str,
            officeId=office_id_str,
            officeName=home_office_name or "",
            chartNumber=chart_number,
            ssn="***-**-****",  # Masked for security
            emergencyContact=emergency_contact,
            emergencyPhone=emergency_phone
        ))
    
    return results, total


# ==================================================
# PATIENT DETAILS SERVICE
# ==================================================

@cache_result(ttl=CACHE_TTL["patient_details"], prefix="patient")
def get_patient_details(
    db: Session,
    patient_id: str  # Can be ID or chart_no
) -> Optional[PatientDetailsResponse]:
    """
    Get complete patient details including all related data.
    
    Args:
        db: Database session
        patient_id: Patient ID (integer) or chart number (string)
    
    Returns:
        PatientDetailsResponse or None if not found
    """
    # Try to parse as integer first, otherwise treat as chart_no
    # Use eager loading to prevent N+1 queries
    try:
        patient_id_int = int(patient_id)
        patient = db.query(Patient).options(
            selectinload(Patient.address),
            selectinload(Patient.contact_info),
            selectinload(Patient.responsible_party),
            selectinload(Patient.insurance_records),
            selectinload(Patient.account_members),
            selectinload(Patient.balance),
            selectinload(Patient.clinical_info),
            selectinload(Patient.medical_alerts),
            joinedload(Patient.home_office)
        ).filter(Patient.id == patient_id_int).first()
    except ValueError:
        patient = db.query(Patient).options(
            selectinload(Patient.address),
            selectinload(Patient.contact_info),
            selectinload(Patient.responsible_party),
            selectinload(Patient.insurance_records),
            selectinload(Patient.account_members),
            selectinload(Patient.balance),
            selectinload(Patient.clinical_info),
            selectinload(Patient.medical_alerts),
            joinedload(Patient.home_office)
        ).filter(Patient.chart_no == patient_id).first()
    
    if not patient:
        return None
    
    # All related data is now eagerly loaded - handle both list and single relationships
    # Note: SQLAlchemy relationships can be lists or single objects depending on model definition
    # Address is uselist=False, so it's a single object or None
    address = getattr(patient, 'address', None)
    
    contact_info = None
    if hasattr(patient, 'contact_info'):
        if isinstance(patient.contact_info, list):
            contact_info = patient.contact_info[0] if patient.contact_info else None
        else:
            contact_info = patient.contact_info
    
    responsible_party = None
    if hasattr(patient, 'responsible_party'):
        if isinstance(patient.responsible_party, list):
            responsible_party = patient.responsible_party[0] if patient.responsible_party else None
        else:
            responsible_party = patient.responsible_party
    
    insurance_records = getattr(patient, 'insurance_records', []) or []
    account_members = getattr(patient, 'account_members', []) or []
    
    balance = None
    if hasattr(patient, 'balance'):
        if isinstance(patient.balance, list):
            balance = patient.balance[0] if patient.balance else None
        else:
            balance = patient.balance
    
    clinical_info = None
    if hasattr(patient, 'clinical_info'):
        if isinstance(patient.clinical_info, list):
            clinical_info = patient.clinical_info[0] if patient.clinical_info else None
        else:
            clinical_info = patient.clinical_info
    
    medical_alerts = getattr(patient, 'medical_alerts', []) or []
    
    # Get appointments (from scheduler_appointments) - separate query as it's from different table
    appointments = db.query(SchedulerAppointment).filter(
        SchedulerAppointment.patient_id == patient.chart_no
    ).order_by(SchedulerAppointment.date.desc(), SchedulerAppointment.start_time.desc()).limit(10).all()
    
    # Build response
    from app.api.v1.patients.schemas import (
        AddressSchema, ContactSchema, OfficeSchema, ProviderSchema,
        FeeScheduleSchema, PatientFlagsSchema, ResponsiblePartySchema,
        InsuranceSchema, InsuranceInfoSchema, AccountMemberSchema,
        AppointmentSchema, BalancesSchema, AgingSchema, ClinicalSchema,
        MedicalAlertSchema, NotesSchema, ReferralSchema, PreferencesSchema
    )
    
    # Build insurance structure
    insurance_data = InsuranceSchema()
    for ins in insurance_records:
        ins_info = InsuranceInfoSchema(
            carrier_name=ins.carrier_name,
            plan_name=ins.plan_name,
            group_number=ins.group_number,
            subscriber_id=ins.subscriber_id,
            subscriber_name=ins.subscriber_name,
            _relationship=getattr(ins, 'relationship_type', None),
            carrier_phone=ins.carrier_phone,
            individual_max_remaining=ins.individual_max_remaining,
            individual_deductible_remaining=ins.individual_deductible_remaining,
            is_active=ins.is_active
        )
        if ins.insurance_type == "primary_dental":
            insurance_data.primary_dental = ins_info
        elif ins.insurance_type == "secondary_dental":
            insurance_data.secondary_dental = ins_info
        elif ins.insurance_type == "primary_medical":
            insurance_data.primary_medical = ins_info
        elif ins.insurance_type == "secondary_medical":
            insurance_data.secondary_medical = ins_info
    
    # Build account members
    account_members_list = []
    for member in account_members:
        member_patient = db.query(Patient).filter(Patient.id == member.member_patient_id).first()
        if member_patient:
            account_members_list.append(AccountMemberSchema(
                id=member_patient.id,
                name=f"{member_patient.last_name}, {member_patient.first_name}",
                age=calculate_age(member_patient.dob),
                gender=member_patient.gender,
                is_active=member_patient.is_active
            ))
    
    # Build appointments list
    appointments_list = []
    for apt in appointments:
        # Get operatory and provider names (simplified - you may need to join actual tables)
        appointments_list.append(AppointmentSchema(
            id=f"APT-{apt.id}",
            date=apt.date,
            time=apt.start_time.strftime("%H:%M") if apt.start_time else "",
            office=apt.office.office_name if apt.office else "",
            operatory=apt.operatory_id,
            procedure=apt.procedure_type,
            provider=apt.provider_id,
            duration=apt.duration,
            status=apt.status.value if hasattr(apt.status, 'value') else str(apt.status),
            last_updated=apt.updated_at.date() if apt.updated_at else date.today(),
            member=f"{patient.last_name}, {patient.first_name}"
        ))
    
    # Build balances
    balances_data = BalancesSchema()
    if balance:
        balances_data.account_balance = balance.account_balance or Decimal("0.00")
        balances_data.last_insurance_payment = balance.last_insurance_payment
        balances_data.last_insurance_payment_date = balance.last_insurance_payment_date
        balances_data.last_patient_payment = balance.last_patient_payment
        balances_data.last_patient_payment_date = balance.last_patient_payment_date
        balances_data.aging = AgingSchema(
            current=balance.current or Decimal("0.00"),
            over_30=balance.over_30 or Decimal("0.00"),
            over_60=balance.over_60 or Decimal("0.00"),
            over_90=balance.over_90 or Decimal("0.00"),
            over_120=balance.over_120 or Decimal("0.00")
        )
    
    # Build clinical info
    clinical_data = ClinicalSchema()
    if clinical_info:
        clinical_data.first_visit = clinical_info.first_visit
        clinical_data.last_visit = clinical_info.last_visit
        clinical_data.next_visit = clinical_info.next_visit
        clinical_data.next_recall = clinical_info.next_recall
        clinical_data.last_pano_chart = clinical_info.last_pano_chart
    
    # Build medical alerts
    medical_alerts_list = [
        MedicalAlertSchema(
            alert=alert.alert,
            date=alert.created_at or datetime.now(),
            entered_by=alert.entered_by or ""
        )
        for alert in medical_alerts
    ]
    clinical_data.medical_alerts = medical_alerts_list
    
    # Get home office info
    home_office_name = None
    home_office_code = None
    if patient.home_office_id and patient.home_office:
        home_office_name = patient.home_office.office_name
        home_office_code = patient.home_office.office_code
    logger.info(f"patient.gender: {patient.gender}")
    logger.info(f"patient: {patient}")
    return PatientDetailsResponse(
        id=patient.id,
        chart_no=patient.chart_no,
        first_name=patient.first_name or "",
        last_name=patient.last_name or "",
        preferred_name=patient.preferred_name,
        dob=patient.dob,
        gender=patient.gender,
        title=patient.title,
        pronouns=patient.pronouns,
        marital_status=patient.marital_status,
        address=AddressSchema(
            address_line_1=address.address_line_1 if address else None,
            address_line_2=address.address_line_2 if address else None,
            city=address.city if address else None,
            state=address.state if address else None,
            zip=address.zip if address else None,
            country=address.country if address else "USA"
        ) if address else AddressSchema(),
        contact=ContactSchema(
            home_phone=contact_info.home_phone if contact_info else None,
            cell_phone=contact_info.cell_phone if contact_info else None,
            work_phone=contact_info.work_phone if contact_info else None,
            email=contact_info.email if contact_info else None,
            preferred_contact=contact_info.preferred_contact if contact_info else None
        ) if contact_info else ContactSchema(email=patient.email),
        office=OfficeSchema(
            home_office_id=patient.home_office_id,
            home_office_name=home_office_name,
            home_office_code=home_office_code
        ),
        provider=ProviderSchema(
            preferred_provider_id=patient.preferred_provider_id,
            preferred_hygienist_id=patient.preferred_hygienist_id
        ),
        fee_schedule=FeeScheduleSchema(
            fee_schedule_id=patient.fee_schedule_id
        ),
        patient_type=patient.patient_type or "General",
        patient_flags=PatientFlagsSchema(
            is_active=patient.is_active,
            is_ortho=patient.is_ortho,
            is_child=patient.is_child,
            is_collection_problem=patient.is_collection_problem,
            is_employee_family=patient.is_employee_family,
            is_short_notice=patient.is_short_notice,
            is_senior=patient.is_senior,
            is_spanish_speaking=patient.is_spanish_speaking,
            assign_benefits=patient.assign_benefits,
            hipaa_agreement=patient.hipaa_agreement,
            no_correspondence=patient.no_correspondence,
            no_auto_email=patient.no_auto_email,
            no_auto_sms=patient.no_auto_sms,
            add_to_quickfill=patient.add_to_quickfill
        ),
        responsible_party=ResponsiblePartySchema(
            id=f"RP-{responsible_party.id}" if responsible_party else None,
            name=responsible_party.name if responsible_party else None,
            type=responsible_party.type if responsible_party else None,
            _relationship=getattr(responsible_party, 'relationship_type', None) if responsible_party else None,
            phone=responsible_party.phone if responsible_party else None,
            email=responsible_party.email if responsible_party else None,
            home_office=responsible_party.home_office.office_name if responsible_party and responsible_party.home_office else None
        ) if responsible_party else ResponsiblePartySchema(),
        insurance=insurance_data,
        account_members=account_members_list,
        appointments=appointments_list,
        recalls=[],  # TODO: Implement recalls
        balances=balances_data,
        clinical=clinical_data,
        notes=NotesSchema(
            patient_notes=patient.patient_notes,
            hipaa_sharing=patient.hipaa_sharing
        ),
        referral=ReferralSchema(
            referral_type=patient.referral_type,
            referred_by=patient.referred_by,
            referred_to=patient.referred_to,
            referral_to_date=patient.referral_to_date
        ),
        preferences=PreferencesSchema(
            preferred_language=patient.preferred_language,
            contact_preference=patient.preferred_contact
        ),
        guardian_name=patient.guardian_name,
        guardian_phone=patient.guardian_phone,
        created_at=patient.created_at or datetime.now(),
        updated_at=patient.updated_at,
        created_by = patient.created_by,
        updated_by = patient.updated_by
    )


# ==================================================
# PATIENT CREATE/UPDATE SERVICE
# ==================================================

def create_patient_full(
    db: Session,
    payload: PatientCreateRequest,
    current_user,
    auto_generate_chart_no: bool = True
) -> PatientDetailsResponse:
    """
    Create a new patient with complete information.
    
    Args:
        db: Database session
        payload: Patient creation data
        auto_generate_chart_no: Auto-generate chart number if not provided
    
    Returns:
        Created patient details
    """
    # Generate chart number if needed
    chart_no = None
    if auto_generate_chart_no:
        chart_no = generate_chart_no(db)
    
    # Create patient record
    patient = Patient(
        chart_no=chart_no,
        first_name=payload.identity.first_name,
        last_name=payload.identity.last_name,
        preferred_name=payload.identity.preferred_name,
        dob=payload.identity.dob,
        gender=payload.identity.gender,
        title=payload.identity.title,
        pronouns=payload.identity.pronouns,
        marital_status=payload.identity.marital_status,
        home_office_id=payload.office.home_office_id,
        preferred_provider_id=payload.provider.preferred_provider_id if payload.provider else None,
        preferred_hygienist_id=payload.provider.preferred_hygienist_id if payload.provider else None,
        fee_schedule_id=payload.fee_schedule.fee_schedule_id if payload.fee_schedule else None,
        patient_type=payload.patient_type,
        is_ortho=payload.patient_flags.is_ortho if payload.patient_flags else False,
        is_child=payload.patient_flags.is_child if payload.patient_flags else False,
        is_collection_problem=payload.patient_flags.is_collection_problem if payload.patient_flags else False,
        is_employee_family=payload.patient_flags.is_employee_family if payload.patient_flags else False,
        is_short_notice=payload.patient_flags.is_short_notice if payload.patient_flags else False,
        is_senior=payload.patient_flags.is_senior if payload.patient_flags else False,
        is_spanish_speaking=payload.patient_flags.is_spanish_speaking if payload.patient_flags else False,
        assign_benefits=payload.patient_flags.assign_benefits if payload.patient_flags else True,
        hipaa_agreement=payload.patient_flags.hipaa_agreement if payload.patient_flags else False,
        no_correspondence=payload.patient_flags.no_correspondence if payload.patient_flags else False,
        no_auto_email=payload.patient_flags.no_auto_email if payload.patient_flags else False,
        no_auto_sms=payload.patient_flags.no_auto_sms if payload.patient_flags else False,
        add_to_quickfill=payload.patient_flags.add_to_quickfill if payload.patient_flags else False,
        preferred_language="English",  # Default, can be updated later
        preferred_contact=payload.contact.preferred_contact if payload.contact else None,
        referral_type=payload.referral.referral_type if payload.referral else None,
        referred_by=payload.referral.referred_by if payload.referral else None,
        referred_to=payload.referral.referred_to if payload.referral else None,
        referral_to_date=payload.referral.referral_to_date if payload.referral else None,
        guardian_name=payload.guardian.guardian_name if payload.guardian else None,
        guardian_phone=payload.guardian.guardian_phone if payload.guardian else None,
        patient_notes=payload.notes.patient_notes if payload.notes else None,
        hipaa_sharing=payload.notes.hipaa_sharing if payload.notes else "Full sharing allowed",
        created_by = current_user.username,
        updated_by = current_user.username

    )
    
    # Set legacy fields for backward compatibility
    if payload.contact:
        patient.phone = payload.contact.home_phone or payload.contact.cell_phone or payload.contact.work_phone
        patient.email = payload.contact.email
    
    db.add(patient)
    db.flush()  # Get patient.id
    
    # Create address
    if payload.address:
        address = PatientAddress(
            patient_id=patient.id,
            address_line_1=payload.address.address_line_1,
            address_line_2=payload.address.address_line_2,
            city=payload.address.city,
            state=payload.address.state,
            zip=payload.address.zip,
            country=payload.address.country or "USA"
        )
        db.add(address)
    
    # Create contact info
    if payload.contact:
        contact_info = PatientContactInfo(
            patient_id=patient.id,
            home_phone=payload.contact.home_phone,
            cell_phone=payload.contact.cell_phone,
            work_phone=payload.contact.work_phone,
            email=payload.contact.email,
            preferred_contact=payload.contact.preferred_contact
        )
        db.add(contact_info)
    
    # Create responsible party
    if payload.responsible_party and payload.responsible_party.responsible_party_id:
        responsible_party = ResponsibleParty(
            patient_id=patient.id,
            responsible_party_id=payload.responsible_party.responsible_party_id,
            relationship_type=payload.responsible_party._relationship,
            name=f"{patient.last_name}, {patient.first_name} (Self)" if payload.responsible_party._relationship == "Self" else None
        )
        db.add(responsible_party)
    
    # Create insurance records
    if payload.coverage:
        if payload.coverage.primary_dental:
            insurance = PatientInsurance(
                patient_id=patient.id,
                insurance_type="primary_dental",
                is_active=True
            )
            db.add(insurance)
        if payload.coverage.secondary_dental:
            insurance = PatientInsurance(
                patient_id=patient.id,
                insurance_type="secondary_dental",
                is_active=True
            )
            db.add(insurance)
        if payload.coverage.primary_medical:
            insurance = PatientInsurance(
                patient_id=patient.id,
                insurance_type="primary_medical",
                is_active=True
            )
            db.add(insurance)
        if payload.coverage.secondary_medical:
            insurance = PatientInsurance(
                patient_id=patient.id,
                insurance_type="secondary_medical",
                is_active=True
            )
            db.add(insurance)
    
    # Create balance record
    if payload.starting_balances:
        balance = PatientBalance(
            patient_id=patient.id,
            current=payload.starting_balances.current,
            over_30=payload.starting_balances.over_30,
            over_60=payload.starting_balances.over_60,
            over_90=payload.starting_balances.over_90,
            over_120=payload.starting_balances.over_120
        )
        db.add(balance)
    else:
        balance = PatientBalance(patient_id=patient.id)
        db.add(balance)
    
    # Create clinical info
    clinical_info = PatientClinicalInfo(patient_id=patient.id)
    db.add(clinical_info)

    
    db.commit()
    db.refresh(patient)
    
    # Return full patient details
    return get_patient_details(db, str(patient.id))


# def update_patient_full(
#     db: Session,
#     patient_id: str,
#     payload: PatientUpdateRequest
# ) -> Optional[PatientDetailsResponse]:
#     """
#     Update an existing patient with complete information.
    
#     Args:
#         db: Database session
#         patient_id: Patient ID or chart number
#         payload: Update data (all fields optional)
    
#     Returns:
#         Updated patient details or None if not found
#     """
#     # Find patient
#     try:
#         patient_id_int = int(patient_id)
#         patient = db.query(Patient).filter(Patient.id == patient_id_int).first()
#     except ValueError:
#         patient = db.query(Patient).filter(Patient.chart_no == patient_id).first()
    
#     if not patient:
#         return None
    
#     # Update patient fields
#     if payload.identity:
#         if payload.identity.first_name:
#             patient.first_name = payload.identity.first_name
#         if payload.identity.last_name:
#             patient.last_name = payload.identity.last_name
#         if payload.identity.preferred_name is not None:
#             patient.preferred_name = payload.identity.preferred_name
#         if payload.identity.dob:
#             patient.dob = payload.identity.dob
#         if payload.identity.gender:
#             patient.gender = payload.identity.gender
#         if payload.identity.title:
#             patient.title = payload.identity.title
#         if payload.identity.pronouns:
#             patient.pronouns = payload.identity.pronouns
#         if payload.identity.marital_status:
#             patient.marital_status = payload.identity.marital_status
    
#     if payload.office:
#         patient.home_office_id = payload.office.home_office_id
    
#     if payload.provider:
#         if payload.provider.preferred_provider_id:
#             patient.preferred_provider_id = payload.provider.preferred_provider_id
#         if payload.provider.preferred_hygienist_id:
#             patient.preferred_hygienist_id = payload.provider.preferred_hygienist_id
    
#     if payload.fee_schedule:
#         patient.fee_schedule_id = payload.fee_schedule.fee_schedule_id
    
#     if payload.patient_type:
#         patient.patient_type = payload.patient_type
    
#     if payload.patient_flags:
#         if payload.patient_flags.is_ortho is not None:
#             patient.is_ortho = payload.patient_flags.is_ortho
#         if payload.patient_flags.is_child is not None:
#             patient.is_child = payload.patient_flags.is_child
#         # ... update other flags similarly
    
#     if payload.referral:
#         if payload.referral.referral_type:
#             patient.referral_type = payload.referral.referral_type
#         if payload.referral.referred_by:
#             patient.referred_by = payload.referral.referred_by
#         if payload.referral.referred_to:
#             patient.referred_to = payload.referral.referred_to
#         if payload.referral.referral_to_date:
#             patient.referral_to_date = payload.referral.referral_to_date
    
#     if payload.guardian:
#         if payload.guardian.guardian_name:
#             patient.guardian_name = payload.guardian.guardian_name
#         if payload.guardian.guardian_phone:
#             patient.guardian_phone = payload.guardian.guardian_phone
    
#     if payload.notes:
#         if payload.notes.patient_notes:
#             patient.patient_notes = payload.notes.patient_notes
#         if payload.notes.hipaa_sharing:
#             patient.hipaa_sharing = payload.notes.hipaa_sharing
    
#     # Update address
#     if payload.address:
#         address = db.query(PatientAddress).filter(PatientAddress.patient_id == patient.id).first()
#         if address:
#             if payload.address.address_line_1:
#                 address.address_line_1 = payload.address.address_line_1
#             if payload.address.address_line_2 is not None:
#                 address.address_line_2 = payload.address.address_line_2
#             # ... update other address fields
#         else:
#             address = PatientAddress(patient_id=patient.id, **payload.address.model_dump(exclude_unset=True))
#             db.add(address)
    
#     # Update contact info
#     if payload.contact:
#         contact_info = db.query(PatientContactInfo).filter(PatientContactInfo.patient_id == patient.id).first()
#         if contact_info:
#             if payload.contact.home_phone:
#                 contact_info.home_phone = payload.contact.home_phone
#             if payload.contact.cell_phone:
#                 contact_info.cell_phone = payload.contact.cell_phone
#             # ... update other contact fields
#         else:
#             contact_info = PatientContactInfo(patient_id=patient.id, **payload.contact.model_dump(exclude_unset=True))
#             db.add(contact_info)
    
#     db.commit()
#     db.refresh(patient)
    
#     return get_patient_details(db, str(patient.id))

def update_patient_full(
    db: Session,
    patient_id: str,
    payload: PatientUpdateRequest,
    current_user
) -> Optional[PatientDetailsResponse]:

    # Find patient
    try:
        patient_id_int = int(patient_id)
        patient = db.query(Patient).filter(Patient.id == patient_id_int).first()
    except ValueError:
        patient = db.query(Patient).filter(Patient.chart_no == patient_id).first()

    if not patient:
        return None

    # -------------------------------
    # Core patient fields
    # -------------------------------
    if payload.identity:
        for field in [
            "first_name", "last_name", "preferred_name",
            "dob", "gender", "title", "pronouns", "marital_status","ssn", "medi_id"
        ]:
            value = getattr(payload.identity, field)
            if value is not None:
                setattr(patient, field, value)

    if payload.office and payload.office.home_office_id is not None:
        patient.home_office_id = payload.office.home_office_id

    if payload.provider:
        if payload.provider.preferred_provider_id is not None:
            patient.preferred_provider_id = payload.provider.preferred_provider_id
        if payload.provider.preferred_hygienist_id is not None:
            patient.preferred_hygienist_id = payload.provider.preferred_hygienist_id

    if payload.fee_schedule and payload.fee_schedule.fee_schedule_id is not None:
        patient.fee_schedule_id = payload.fee_schedule.fee_schedule_id

    if payload.patient_type is not None:
        patient.patient_type = payload.patient_type


    # -------------------------------
    # Flags
    # -------------------------------
    if payload.patient_flags:
        for field in [
            "is_ortho", "is_child", "is_collection_problem",
            "is_employee_family", "is_short_notice",
            "is_senior", "is_spanish_speaking",
            "assign_benefits", "hipaa_agreement",
            "no_correspondence", "no_auto_email",
            "no_auto_sms", "add_to_quickfill"
        ]:
            value = getattr(payload.patient_flags, field)
            if value is not None:
                setattr(patient, field, value)

    # -------------------------------
    # Referral
    # -------------------------------
    if payload.referral:
        for field in [
            "referral_type", "referred_by",
            "referred_to", "referral_to_date"
        ]:
            value = getattr(payload.referral, field)
            if value is not None:
                setattr(patient, field, value)

    # -------------------------------
    # Guardian
    # -------------------------------
    if payload.guardian:
        if payload.guardian.guardian_name is not None:
            patient.guardian_name = payload.guardian.guardian_name
        if payload.guardian.guardian_phone is not None:
            patient.guardian_phone = payload.guardian.guardian_phone

    # -------------------------------
    # Notes
    # -------------------------------
    if payload.notes:
        if payload.notes.patient_notes is not None:
            patient.patient_notes = payload.notes.patient_notes
        if payload.notes.hipaa_sharing is not None:
            patient.hipaa_sharing = payload.notes.hipaa_sharing

    # -------------------------------
    # Address
    # -------------------------------
    if payload.address:
        address = db.query(PatientAddress).filter_by(patient_id=patient.id).first()
        if not address:
            address = PatientAddress(patient_id=patient.id)
            db.add(address)

        for field in [
            "address_line_1", "address_line_2",
            "city", "state", "zip", "country"
        ]:
            value = getattr(payload.address, field)
            if value is not None:
                setattr(address, field, value)

    # -------------------------------
    # Contact info (and legacy sync)
    # -------------------------------
    if payload.contact:
        contact = db.query(PatientContactInfo).filter_by(patient_id=patient.id).first()
        if not contact:
            contact = PatientContactInfo(patient_id=patient.id)
            db.add(contact)

        for field in [
            "home_phone", "cell_phone",
            "work_phone", "email",
            "preferred_contact"
        ]:
            value = getattr(payload.contact, field)
            if value is not None:
                setattr(contact, field, value)

        # legacy fields
        patient.phone = (
            contact.home_phone or
            contact.cell_phone or
            contact.work_phone
        )
        patient.email = contact.email

    # -------------------------------
    # Responsible party
    # -------------------------------
    if payload.responsible_party and payload.responsible_party.responsible_party_id:
        rp = db.query(ResponsibleParty).filter_by(patient_id=patient.id).first()
        if not rp:
            rp = ResponsibleParty(patient_id=patient.id)
            db.add(rp)

        if payload.responsible_party.responsible_party_id is not None:
            rp.responsible_party_id = payload.responsible_party.responsible_party_id

        if payload.responsible_party._relationship is not None:
            rp.relationship_type = payload.responsible_party._relationship

    # -------------------------------
    # Insurance (replace strategy)
    # -------------------------------
    if payload.coverage:
        db.query(PatientInsurance).filter_by(patient_id=patient.id).delete()

        if payload.coverage.primary_dental:
            db.add(PatientInsurance(patient_id=patient.id, insurance_type="primary_dental", is_active=True))
        if payload.coverage.secondary_dental:
            db.add(PatientInsurance(patient_id=patient.id, insurance_type="secondary_dental", is_active=True))
        if payload.coverage.primary_medical:
            db.add(PatientInsurance(patient_id=patient.id, insurance_type="primary_medical", is_active=True))
        if payload.coverage.secondary_medical:
            db.add(PatientInsurance(patient_id=patient.id, insurance_type="secondary_medical", is_active=True))

    # -------------------------------
    # Balance
    # -------------------------------
    if payload.starting_balances:
        balance = db.query(PatientBalance).filter_by(patient_id=patient.id).first()
        if not balance:
            balance = PatientBalance(patient_id=patient.id)
            db.add(balance)

        for field in ["current", "over_30", "over_60", "over_90", "over_120"]:
            value = getattr(payload.starting_balances, field)
            if value is not None:
                setattr(balance, field, value)

    # -------------------------------
    # Clinical info (exists guarantee)
    # -------------------------------
    clinical = db.query(PatientClinicalInfo).filter_by(patient_id=patient.id).first()
    if not clinical:
        db.add(PatientClinicalInfo(patient_id=patient.id))
    
    # Invalidate cache for this patient after update
    try:
        invalidate_cache(f"patient:get_patient_details:*{patient_id}*")
        invalidate_cache("patient:search_patients:*")
    except:
        pass  # Cache invalidation is optional

    # -------------------------------
    # AUDIT (single line, critical)
    # -------------------------------
    patient.updated_by = current_user.username


    db.commit()
    db.refresh(patient)
    return get_patient_details(db, str(patient.id))


# ==================================================
# METADATA SERVICES
# ==================================================

def get_fee_schedules(
    db: Session,
    office_id: Optional[int] = None
) -> FeeSchedulesResponse:
    """Get fee schedules metadata."""
    query = db.query(FeeSchedule).filter(FeeSchedule.is_active == True)
    
    if office_id:
        query = query.filter(FeeSchedule.office_id == office_id)
    
    fee_schedules = query.all()
    
    results = []
    for fs in fee_schedules:
        office_name = None
        if fs.office_id and fs.office:
            office_name = fs.office.office_name
        
        results.append(FeeScheduleMetadata(
            fee_schedule_id=fs.fee_schedule_id,
            fee_schedule_name=fs.fee_schedule_name,
            description=fs.description,
            office_id=fs.office_id,
            office_name=office_name
        ))
    
    return FeeSchedulesResponse(fee_schedules=results)


@cache_result(ttl=CACHE_TTL["metadata"], prefix="metadata")
def get_patient_types(db: Session) -> PatientTypesResponse:
    """Get patient types metadata."""
    patient_types = db.query(PatientType).filter(PatientType.is_active == True).all()
    
    results = [
        PatientTypeMetadata(
            code=pt.code,
            name=pt.name,
            description=pt.description
        )
        for pt in patient_types
    ]
    
    return PatientTypesResponse(patient_types=results)


@cache_result(ttl=CACHE_TTL["metadata"], prefix="metadata")
def get_referral_types(db: Session) -> ReferralTypesResponse:
    """Get referral types metadata."""
    referral_types = db.query(ReferralType).filter(ReferralType.is_active == True).all()
    
    results = [
        ReferralTypeMetadata(
            code=rt.code,
            name=rt.name,
            description=rt.description
        )
        for rt in referral_types
    ]
    
    return ReferralTypesResponse(referral_types=results)


@cache_result(ttl=CACHE_TTL["metadata"], prefix="metadata")
def get_responsible_party_relationships(db: Session) -> RelationshipsResponse:
    """Get responsible party relationships metadata."""
    relationships = db.query(ResponsiblePartyRelationship).filter(
        ResponsiblePartyRelationship.is_active == True
    ).all()
    
    results = [
        RelationshipMetadata(
            code=r.code,
            name=r.name,
            description=r.description
        )
        for r in relationships
    ]
    
    return RelationshipsResponse(relationships=results)


@cache_result(ttl=CACHE_TTL["metadata"], prefix="metadata")
def get_contact_preferences(db: Session) -> ContactPreferencesResponse:
    """Get contact preferences metadata."""
    preferences = db.query(ContactPreference).filter(ContactPreference.is_active == True).all()
    
    results = [
        ContactPreferenceMetadata(
            code=cp.code,
            name=cp.name
        )
        for cp in preferences
    ]
    
    return ContactPreferencesResponse(contact_preferences=results)


@cache_result(ttl=CACHE_TTL["metadata"], prefix="metadata")
def get_titles(db: Session) -> TitlesResponse:
    """Get titles metadata."""
    titles = db.query(Title).filter(Title.is_active == True).order_by(Title.display_order).all()
    
    results = [
        TitleMetadata(
            code=t.code,
            name=t.name,
            description=t.description
        )
        for t in titles
    ]
    
    return TitlesResponse(titles=results)


@cache_result(ttl=CACHE_TTL["metadata"], prefix="metadata")
def get_pronouns(db: Session) -> PronounsResponse:
    """Get pronouns metadata."""
    pronouns = db.query(Pronoun).filter(Pronoun.is_active == True).order_by(Pronoun.display_order).all()
    
    results = [
        PronounMetadata(
            code=p.code,
            name=p.name,
            description=p.description
        )
        for p in pronouns
    ]
    
    return PronounsResponse(pronouns=results)


@cache_result(ttl=CACHE_TTL["metadata"], prefix="metadata")
def get_states(db: Session) -> StatesResponse:
    """Get US states metadata."""
    states = db.query(State).filter(State.is_active == True).order_by(State.display_order).all()
    
    results = [
        StateMetadata(
            code=s.code,
            name=s.name
        )
        for s in states
    ]
    
    return StatesResponse(states=results)


@cache_result(ttl=CACHE_TTL["metadata"], prefix="metadata")
def get_marital_statuses(db: Session) -> MaritalStatusesResponse:
    """Get marital statuses metadata."""
    statuses = db.query(MaritalStatus).filter(MaritalStatus.is_active == True).order_by(MaritalStatus.display_order).all()
    
    results = [
        MaritalStatusMetadata(
            code=ms.code,
            name=ms.name,
            description=ms.description
        )
        for ms in statuses
    ]
    
    return MaritalStatusesResponse(marital_statuses=results)


@cache_result(ttl=CACHE_TTL["metadata"], prefix="metadata")
def get_genders(db: Session) -> GendersResponse:
    """Get genders metadata."""
    genders = db.query(Gender).filter(Gender.is_active == True).order_by(Gender.display_order).all()
    
    results = [
        GenderMetadata(
            code=g.code,
            name=g.name,
            description=g.description
        )
        for g in genders
    ]
    
    return GendersResponse(genders=results)


@cache_result(ttl=CACHE_TTL["metadata"], prefix="metadata")
def get_all_patient_metadata(
    db: Session,
    office_id: Optional[int] = None
) -> PatientMetadataResponse:
    """Get all patient metadata in a single call."""
    return PatientMetadataResponse(
        titles=[TitleMetadata(code=t.code, name=t.name, description=t.description) 
                for t in db.query(Title).filter(Title.is_active == True).order_by(Title.display_order).all()],
        pronouns=[PronounMetadata(code=p.code, name=p.name, description=p.description) 
                  for p in db.query(Pronoun).filter(Pronoun.is_active == True).order_by(Pronoun.display_order).all()],
        states=[StateMetadata(code=s.code, name=s.name) 
                for s in db.query(State).filter(State.is_active == True).order_by(State.display_order).all()],
        marital_statuses=[MaritalStatusMetadata(code=ms.code, name=ms.name, description=ms.description) 
                          for ms in db.query(MaritalStatus).filter(MaritalStatus.is_active == True).order_by(MaritalStatus.display_order).all()],
        genders=[GenderMetadata(code=g.code, name=g.name, description=g.description) 
                 for g in db.query(Gender).filter(Gender.is_active == True).order_by(Gender.display_order).all()],
        responsible_party_relationships=[RelationshipMetadata(code=r.code, name=r.name, description=r.description) 
                                         for r in db.query(ResponsiblePartyRelationship).filter(ResponsiblePartyRelationship.is_active == True).all()],
        contact_preferences=[ContactPreferenceMetadata(code=cp.code, name=cp.name) 
                             for cp in db.query(ContactPreference).filter(ContactPreference.is_active == True).all()],
        referral_types=[ReferralTypeMetadata(code=rt.code, name=rt.name, description=rt.description) 
                        for rt in db.query(ReferralType).filter(ReferralType.is_active == True).all()],
        patient_types=[PatientTypeMetadata(code=pt.code, name=pt.name, description=pt.description) 
                       for pt in db.query(PatientType).filter(PatientType.is_active == True).all()],
        fee_schedules=[FeeScheduleMetadata(
            fee_schedule_id=fs.fee_schedule_id,
            fee_schedule_name=fs.fee_schedule_name,
            description=fs.description,
            office_id=fs.office_id,
            office_name=fs.office.office_name if fs.office else None
        ) for fs in db.query(FeeSchedule).filter(
            FeeSchedule.is_active == True,
            FeeSchedule.office_id == office_id if office_id else True
        ).all()]
    )


# ==================================================
# DUPLICATE CHECK SERVICE
# ==================================================

def check_duplicate_patient(
    db: Session,
    payload: DuplicateCheckRequest
) -> DuplicateCheckResponse:
    """
    Check if a patient with similar information already exists.
    
    Args:
        db: Database session
        payload: Patient information to check
    
    Returns:
        DuplicateCheckResponse with matches
    """
    duplicates = []
    
    # Search by name and DOB
    query = db.query(Patient).filter(
        Patient.first_name.ilike(f"%{payload.firstName}%"),
        Patient.last_name.ilike(f"%{payload.lastName}%")
    )
    
    if payload.birthdate:
        query = query.filter(Patient.dob == payload.birthdate)
    
    matches = query.all()

    logger.info(f"matches  =======================> {matches}")
    
    for match in matches:
        match_reasons = []
        match_score = 0.0

        logger.info(f"match.first_name.lower()======={ payload.firstName.lower()}=======================>{match.first_name.lower()}")
        logger.info(f"match.last_name.lower()====={payload.lastName.lower()}=======================>{match.last_name.lower()}")
    
        
        # Name match
        if match.first_name.lower() == payload.firstName.lower() and \
           match.last_name.lower() == payload.lastName.lower():
            match_reasons.append("Name match")
            match_score += 0.5
        logger.info(f" match.dob====={match.dob}=======================>{payload.birthdate}")
    
        # DOB match
        if payload.birthdate and match.dob == payload.birthdate:
            match_reasons.append("DOB match")
            match_score += 0.3
        
        # Phone match
        if payload.phone:
            normalized_payload_phone = normalize_phone(payload.phone)
            match_phone = normalize_phone(match.phone)
            if match_phone and normalized_payload_phone and match_phone == normalized_payload_phone:
                match_reasons.append("Phone match")
                match_score += 0.1
            
            # Check contact_info
            contact_info = db.query(PatientContactInfo).filter(
                PatientContactInfo.patient_id == match.id
            ).first()
            if contact_info:
                for phone_field in [contact_info.home_phone, contact_info.cell_phone, contact_info.work_phone]:
                    if phone_field:
                        normalized_match_phone = normalize_phone(phone_field)
                        if normalized_match_phone and normalized_payload_phone and normalized_match_phone == normalized_payload_phone:
                            match_reasons.append("Phone match")
                            match_score += 0.1
                            break
        
        # Email match
        if payload.email:
            if match.email and match.email.lower() == payload.email.lower():
                match_reasons.append("Email match")
                match_score += 0.1
            
            # Check contact_info
            contact_info = db.query(PatientContactInfo).filter(
                PatientContactInfo.patient_id == match.id
            ).first()
            if contact_info and contact_info.email and contact_info.email.lower() == payload.email.lower():
                match_reasons.append("Email match")
                match_score += 0.1
        logger.info(f" match_score============================>{match_score}")
        if match_score > 0:
            logger.info(f" appending for ============================>{match_score}")
            duplicates.append(DuplicateMatchSchema(
                id=match.id,
                chart_no=match.chart_no,
                name=f"{match.last_name}, {match.first_name}",
                dob=match.dob,
                phone=match.phone,
                match_score=min(match_score, 1.0),
                match_reasons=match_reasons
            ))

            logger.info(f" duplicates for ============================>{duplicates}")
    
    # Sort by match score descending
    duplicates.sort(key=lambda x: x.match_score, reverse=True)
    
    return DuplicateCheckResponse(
        has_duplicates=len(duplicates) > 0,
        duplicates=duplicates
    )


# ==================================================
# LEGACY FUNCTIONS (for backward compatibility)
# ==================================================

def create_patient(
    db: Session, 
    payload: PatientCreate,
    auto_generate_chart_no: bool = True
) -> PatientResponse:
    """Legacy create patient function."""
    if payload.chart_no:
        existing = db.query(Patient).filter(Patient.chart_no == payload.chart_no).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Patient with chart number '{payload.chart_no}' already exists"
            )
    elif auto_generate_chart_no:
        payload.chart_no = generate_chart_no(db)
    
    patient_data = payload.model_dump(exclude_unset=True)
    patient = Patient(**patient_data)
    
    db.add(patient)
    db.commit()
    db.refresh(patient)
    
    return _patient_to_response(patient)


def list_patients(
    db: Session,
    search: Optional[str] = None,
    limit: Optional[int] = 100,
    offset: Optional[int] = 0
) -> tuple[List[PatientResponse], int]:
    """Legacy list patients function."""
    query = db.query(Patient)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Patient.first_name.ilike(search_term),
                Patient.last_name.ilike(search_term),
                Patient.chart_no.ilike(search_term),
                Patient.phone.ilike(search_term),
                Patient.email.ilike(search_term)
            )
        )
    
    total = query.count()
    query = query.order_by(Patient.created_at.desc())
    
    if limit:
        query = query.limit(limit)
    if offset:
        query = query.offset(offset)
    
    patients = query.all()
    return [_patient_to_response(p) for p in patients], total


def get_patient(db: Session, patient_id: int) -> Optional[PatientResponse]:
    """Legacy get patient function."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        return None
    return _patient_to_response(patient)


def get_patient_by_chart_no(db: Session, chart_no: str) -> Optional[PatientResponse]:
    """Legacy get patient by chart number function."""
    patient = db.query(Patient).filter(Patient.chart_no == chart_no).first()
    if not patient:
        return None
    return _patient_to_response(patient)


def update_patient(
    db: Session, 
    patient_id: int, 
    payload: PatientUpdate
) -> Optional[PatientResponse]:
    """Legacy update patient function."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        return None
    
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(patient, field, value)
    
    db.commit()
    db.refresh(patient)
    
    return _patient_to_response(patient)


def delete_patient(db: Session, patient_id: int) -> bool:
    """Legacy delete patient function."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        return False
    
    db.delete(patient)
    db.commit()
    return True


def _patient_to_response(patient: Patient) -> PatientResponse:
    """Convert Patient model to legacy PatientResponse schema."""
    return PatientResponse(
        id=patient.id,
        chart_no=patient.chart_no,
        first_name=patient.first_name or "",
        last_name=patient.last_name or "",
        dob=patient.dob,
        gender=patient.gender,
        phone=patient.phone,
        email=patient.email,
        home_office_id=patient.home_office_id,
        created_at=patient.created_at.isoformat() if patient.created_at else None,
        updated_at=patient.updated_at.isoformat() if patient.updated_at else None
    )
