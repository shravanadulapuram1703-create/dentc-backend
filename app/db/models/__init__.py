"""Model registry.

Importing this package registers every ORM class on ``Base.metadata`` (needed by
Alembic autogenerate and by the app at startup). Add new domain modules here.
"""

from app.db.models.access import (
    Notification,
    Permission,
    UserGroup,
    UserGroupMembership,
    UserGroupRight,
    UserIpRule,
    UserLoginRestriction,
    UserPreference,
    UserTask,
    UserTimeClockConfig,
)
from app.db.models.appointnow import AppointNowReason, BookingRequest
from app.db.models.platform import SupportTicket, UtilityRun
from app.db.models.account import (
    AccountCommunications,
    AccountConsent,
    AccountHoliday,
    AccountSettings,
    OfficePhoneAssignment,
)
from app.db.models.audit import AuditLog
from app.db.models.aux_codes import IcdCode, PlaceOfServiceCode
from app.db.models.patient_extra import (
    ClaimAttachment,
    PatientAdjustment,
    PatientConsent,
    PatientDocument,
    PatientEmergencyContact,
    ProgressNoteAttachment,
)
from app.db.models.restorative import (
    ChartSettings,
    ChartStatusTemplate,
    ChartToothNote,
)
from app.db.models.office_assignment import (
    OfficeCodeBundle,
    OfficeLetterTemplate,
    OfficeNoteMacro,
    OfficePrescriptionLibrary,
    OfficeProcedureCode,
    OfficeProductionType,
    ProductionType,
    ProviderOffice,
)
from app.db.models.office_setup import (
    OfficeAdvancedSettings,
    OfficeIntegrations,
    OfficeScheduleDay,
    OfficeSmartAssist,
    OfficeSmartAssistItem,
    OfficeStatementSettings,
)
from app.db.models.procedure_setup import (
    ProcedureInsuranceRule,
    ProviderProcedureCode,
)
from app.db.models.provider_setup import (
    ProviderCarrierLogin,
    ProviderHoliday,
    ProviderReferralOffice,
    ProviderScheduleDay,
    ProviderWatermark,
)
from app.db.models.billing import (
    ClaimSubmission,
    ExplosionCode,
    ExplosionCodeItem,
    InsuranceClaim,
    LedgerInsuranceDetail,
    OrthoPlan,
    PatientInsPaymentPlan,
    PatientPayment,
    PatientPaymentPlan,
    PatientPlanInstallment,
    PatientRefund,
    PatientRegPlan,
    PatientSecInsPaymentPlan,
    PatientStatement,
    PaymentAllocation,
)
from app.db.models.clinical import (
    ChartCondition,
    PatientProcedure,
    PerioChartActivity,
    PerioChartSetting,
    PerioChartTemplate,
    PerioExam,
    PerioExamDetail,
    Prescription,
    ProgressNote,
)
from app.db.models.codes import (
    ChartColor,
    ChartMaterial,
    CodeBundle,
    CodeBundleItem,
    CodesView,
    FeeSchedule,
    FeeScheduleEntry,
    NoteMacro,
    PrescriptionLibrary,
    ProcedureCode,
)
from app.db.models.comms import (
    LetterBatchItem,
    LetterBatchRun,
    LetterTemplate,
    PostcardTemplate,
    SmsMessage,
)
from app.db.models.messaging import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageAttachment,
    MessageReaction,
    MessageReceipt,
    MessageRecipientState,
    UserPresence,
)
from app.db.models.identity import (
    AuthActionToken,
    Office,
    OfficeGroup,
    Operatory,
    Provider,
    RefreshToken,
    Tenant,
    User,
    UserOffice,
)
from app.db.models.imaging import (
    CollectionAgency,
    DicomInstance,
    DicomSeries,
    DicomStudy,
    ImageDetail,
    ImageGroup,
    ReferralDemogDetail,
    ReferralDemogHeader,
    StoredObject,
)
from app.db.models.insurance import (
    Employer,
    FeeScheduleAssignment,
    InsCustomCoverage,
    InsuranceCarrier,
    InsuranceCoverageRule,
    InsurancePlan,
    InsuranceSubscriber,
)
from app.db.models.patients import (
    AccountNote,
    CariesRiskAssessment,
    MedicalHistoryDetail,
    MedicalHistoryRecord,
    Patient,
    PatientAlert,
    PatientInsurance,
    PatientMedicalAlert,
    PatientNote,
    PatientOpeningBalance,
    PatientQuestionnaireResponse,
    PatientRecall,
    PatientSignature,
    Referral,
    ResponsibleParty,
)
from app.db.models.reference import (
    Definition,
    DefinitionGroup,
    ImagingTemplate,
    QuestionnaireHeader,
    QuestionnaireOption,
)
from app.db.models.scheduling import Appointment, AppointmentProcedure
from app.db.models.staff import ProviderInsuranceId, ProviderRouteSlip, TimeClockEntry
from app.db.models.treatment import (
    TreatmentPlan,
    TreatmentPlanInsuranceDetail,
    TreatmentPlanItem,
)

__all__ = [
    # audit
    "AuditLog",
    # access (Phase 4 net-new)
    "UserPreference", "UserGroup", "UserGroupMembership", "UserIpRule",
    "UserTimeClockConfig", "UserLoginRestriction", "Permission", "UserGroupRight",
    "UserTask", "Notification",
    # platform (help / utilities)
    "SupportTicket", "UtilityRun",
    # appointnow (external online booking)
    "AppointNowReason", "BookingRequest",
    # patients module net-new
    "PatientDocument", "PatientEmergencyContact", "PatientAdjustment", "ClaimAttachment",
    "ProgressNoteAttachment", "PatientConsent",
    "ChartStatusTemplate", "ChartSettings", "ChartToothNote",
    # account information (Setup -> Account Info)
    "AccountSettings", "AccountCommunications", "OfficePhoneAssignment",
    "AccountHoliday", "AccountConsent",
    # office setup (Setup -> Offices)
    "OfficeStatementSettings", "OfficeIntegrations", "OfficeScheduleDay",
    "OfficeAdvancedSettings", "OfficeSmartAssist", "OfficeSmartAssistItem",
    # provider setup (Setup -> Providers)
    "ProviderScheduleDay", "ProviderHoliday", "ProviderWatermark",
    "ProviderReferralOffice", "ProviderCarrierLogin",
    # procedure code setup (Setup -> Procedure Codes)
    "ProviderProcedureCode", "ProcedureInsuranceRule",
    # auxiliary code tables (Setup -> Procedure Codes)
    "PlaceOfServiceCode", "IcdCode",
    # office assignment (Setup -> Offices -> Office Assignment)
    "ProductionType", "OfficeProcedureCode", "OfficeCodeBundle",
    "OfficeProductionType", "ProviderOffice", "OfficeNoteMacro",
    "OfficePrescriptionLibrary", "OfficeLetterTemplate",
    # identity
    "Tenant", "User", "RefreshToken", "AuthActionToken", "Office", "Provider",
    "Operatory", "UserOffice", "OfficeGroup",
    # insurance
    "Employer", "InsuranceCarrier", "InsurancePlan", "InsuranceSubscriber",
    "InsuranceCoverageRule", "InsCustomCoverage", "FeeScheduleAssignment",
    # codes / fees
    "ProcedureCode", "FeeSchedule", "FeeScheduleEntry", "ChartMaterial",
    "NoteMacro", "CodeBundle", "CodeBundleItem", "PrescriptionLibrary",
    "ChartColor", "CodesView",
    # patients
    "Patient", "PatientInsurance", "PatientAlert", "AccountNote",
    "PatientSignature", "MedicalHistoryRecord", "MedicalHistoryDetail",
    "Referral", "PatientNote", "PatientRecall", "CariesRiskAssessment",
    "PatientMedicalAlert", "PatientQuestionnaireResponse", "PatientOpeningBalance",
    "ResponsibleParty",
    # scheduling
    "Appointment", "AppointmentProcedure",
    # treatment
    "TreatmentPlan", "TreatmentPlanItem", "TreatmentPlanInsuranceDetail",
    # clinical
    "PatientProcedure", "ChartCondition", "ProgressNote", "PerioExam",
    "PerioExamDetail", "Prescription", "PerioChartSetting", "PerioChartActivity",
    "PerioChartTemplate",
    # billing
    "PatientPayment", "InsuranceClaim", "ClaimSubmission", "LedgerInsuranceDetail",
    "PaymentAllocation", "PatientPaymentPlan", "PatientInsPaymentPlan",
    "PatientSecInsPaymentPlan", "PatientRegPlan", "OrthoPlan",
    "PatientPlanInstallment", "PatientRefund", "PatientStatement",
    "ExplosionCode", "ExplosionCodeItem",
    # reference / config
    "Definition", "DefinitionGroup", "ImagingTemplate", "QuestionnaireHeader",
    "QuestionnaireOption",
    # communications
    "SmsMessage", "LetterTemplate", "PostcardTemplate",
    "LetterBatchRun", "LetterBatchItem",
    # direct messaging
    "Conversation", "ConversationParticipant", "Message", "MessageReceipt",
    "MessageRecipientState", "MessageAttachment", "MessageReaction", "UserPresence",
    # staff
    "TimeClockEntry", "ProviderInsuranceId", "ProviderRouteSlip",
    # imaging / misc
    "ImageGroup", "ImageDetail", "CollectionAgency", "ReferralDemogHeader",
    "ReferralDemogDetail",
    # DICOM archive (GCS + Postgres index)
    "StoredObject", "DicomStudy", "DicomSeries", "DicomInstance",
]
