# from app.models.offices import Office
# # from app.models.office_statement import OfficeStatement
# from app.models.user import User

# # Core tables FIRST
# # from app.models.user import User
# from app.models.tenant import Tenant
# # from app.models.office import Office
# from app.models.role import Role

# # Mapping tables
# from app.models.user_office import UserOffice
# from app.models.user_ip_rules import UserIPRule

# # Dependent tables LAST
# from app.models.user_preferences import UserPreference

# from app.models.offices import OfficeOperatory,OfficeHoliday,OfficeSchedule

# # from app.models.tenant import Tenant
# # from app.models.user import User
# # from app.models.user_office import UserOffice
# # from app.models.user_preferences import UserPreference
# from app.models.office_role import OfficeRole
# from app.models.role_permission import RolePermission
# # from app.models.user_ip_rule import UserIPRule
# from app.models.user_time_clock import UserTimeClock
# # from app.models.office import Office
# # from app.models.role import Role
# from app.models.permission import Permission
# # from app.models.office_role import OfficeRole
# # from app.models.office_role_permission import OfficeRolePermission
# from app.models.user_role import UserRole
# # from app.models.office_statement import OfficeStatement
# # from app.models.office_integration import OfficeIntegration
# # from app.models.office_schedule import OfficeSchedule
# # from app.models.office_holiday import OfficeHoliday
# # from app.models.operatory import Operatory
# # from app.models.user_permission import UserPermission
# # from app.models.patient import Patient
# # from app.models.appointment import Appointment
# # from app.models.treatment_plan import TreatmentPlan
# # from app.models.treatment_item import TreatmentItem
# # from app.models.treatment_note import TreatmentNote
# # from app.models.attachment import Attachment
# # from app.models.invoice import Invoice
# # from app.models.payment import Payment

# from app.models.role import Role
# from app.models.permission import Permission
# # from app.models.office import Office
# from app.models.associations import (
#     # user_roles_,
#     role_permissions,
#     user_permissions,
# )
# from app.models.user_role import UserRole
# # from app.models.associations.user_role import UserRole
# # from app.models.associations.user_permission import UserPermission

# from app.models.ip_addresses import IPAddress
# # from app.models.user_ip_rules import UserIPRule
# # from app.models.users import User


# from app.models.refresh_token import RefreshToken
# from app.models.audit_log import AuditLog
# from app.models.impersonation_session import ImpersonationSession


# ==================================================
# Core / Base Models
# ==================================================
from app.models.tenant import Tenant
from app.models.user import User
from app.models.role import Role
from app.models.permission import Permission
from app.models.offices import Office

# ==================================================
# Office Related Models
# ==================================================
from app.models.offices import (
    OfficeOperatory,
    OfficeHoliday,
    OfficeOtherInfo,
    # OfficeSchedule,
    # BillingProvider,
    # FeeSchedule
    OfficeIntegrations,
    OfficeImagingSystem,
    OfficePatientUrls,
    OfficePaymentMethod,
    OfficeAdvancedSettings
)



from app.models.office_role import OfficeRole
from app.models.office_role_permission import OfficeRolePermission

# ==================================================
# User Related Models
# ==================================================
from app.models.user_role import UserRole
from app.models.user_office import UserOffice
from app.models.user_preferences import UserPreference
from app.models.user_ip_rules import UserIPRule
from app.models.user_time_clock import UserTimeClock
from app.models.group import Group, UserGroupMembership

# ==================================================
# Role / Permission Mapping
# ==================================================
from app.models.role_permission import RolePermission
from app.models.associations import (
    role_permissions,
    user_permissions,
)

# ==================================================
# Security & Infrastructure
# ==================================================
from app.models.ip_addresses import IPAddress
from app.models.refresh_token import RefreshToken
from app.models.audit_log import AuditLog
from app.models.impersonation_session import ImpersonationSession
from app.models.patient_ledger import (
    PatientLedgerEntry,
    PatientProcedure,
    PatientClaim,
    PatientClaimProcedure,
    PatientClaimEvent,
    PatientClaimAttachment,
    PatientPayment,
    PatientPaymentApplication,
    PatientAdjustment,
    PatientAdjustmentApplication,
    PaymentCode,
    AdjustmentCode,
    ClaimStatus,
    TransactionType,
)

# ==================================================
# Patient Models
# ==================================================
from app.models.patient import (
    Patient,
    PatientAddress,
    PatientContactInfo,
    ResponsibleParty,
    PatientInsurance,
    FeeSchedule,
    PatientType,
    ReferralType,
    ResponsiblePartyRelationship,
    ContactPreference,
    PatientAccountMember,
    PatientBalance,
    PatientClinicalInfo,
    PatientMedicalAlert,
    Title,
    Pronoun,
    State,
    MaritalStatus,
    Gender)




# ==================================================
# Scheduler Models
# ==================================================
from app.api.v1.scheduler.models import (
    SchedulerAppointment,
    SchedulerOperatory,
    SchedulerProvider,
    SchedulerProcedureType,
    SchedulerConfig,
    AppointmentStatusEnum,
    AppointmentStatus,
    AppointmentType,
    ProcedureCode,
    ProcedureCategory,
    TreatmentPlan,
    TreatmentPlanPhase,
    TreatmentPlanProcedure,
    AppointmentTreatment
)