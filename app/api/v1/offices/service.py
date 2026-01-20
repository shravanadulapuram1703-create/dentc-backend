# =========================
# Standard / Logging
# =========================
import logging

# =========================
# FastAPI / SQLAlchemy Core
# =========================
from fastapi import HTTPException
from sqlalchemy import text, distinct, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound

# =========================
# Core Logging
# =========================
from app.core.logging import setup_logging

# =========================
# Models
# =========================
from app.models.offices import (
    Office,
    OfficeOperatory,
    OfficeSchedule,
    OfficeOtherInfo,
    OfficeIntegrations,
    OfficeImagingSystem,
    OfficePatientUrls,
    OfficePaymentMethod,
    OfficeTransworld,
    OfficeAdvancedSettings,
    OfficeStatement
)
from app.models.billing_provider import BillingProvider
from app.models.fee_schedule import FeeSchedule

# =========================
# Schemas – Office
# =========================
from app.api.v1.offices.schemas import (
    OfficePayload,
    Address,
    Contact,
    Billing,
    Settings,
    StatementMessages,
    StatementSettings,
    Operatory,
    SmartAssist,
    # EClaims,
    # Transworld,
    # Imaging,
    # TextMessaging,
    # PatientUrls,
    Integrations,
    OfficeMetadataResponse,
    BillingProviderMeta,
    FeeScheduleMeta,
    
)

# =========================
# Schemas – Billing Provider
# =========================
from app.api.v1.offices.schemas import (
    BillingProviderCreate,
    BillingProviderResponse,
)

# =========================
# Schemas – Fee Schedule
# =========================
from app.api.v1.offices.schemas import (
    FeeScheduleCreate,
    FeeScheduleResponse,
)
from app.models.offices import OfficeHoliday,OfficeSmartAssist#,OfficeSmartAssistItem


logger = setup_logging()
logger = logging.getLogger(__name__)



def get_office_full(db: Session, office_id: int, current_user: User = None) -> OfficePayload:
    office = db.query(Office).filter(Office.id == office_id).first()
    
    
    if not office:
        raise HTTPException(status_code=404, detail="Office not found")
    
    other = office.other_info
    statements = office.statements

    # schedules = office.schedules
    # ============================
    # BUILD SCHEDULE FOR GET
    # ============================
    schedule_data = {}

    
    # off_schedules = office.schedules
    # logger.info(f"office.schedules  =======+++++++++++++>>>>>>>>>>>> {off_schedules}")

    for sch in office.schedules:
        schedule_data[sch.day_of_week.lower()] = {
            "start": sch.start_time,
            "end": sch.end_time,
            "lunchStart": sch.lunch_start,
            "lunchEnd": sch.lunch_end,
            "closed": sch.is_closed,
        }

    logger.info(f"schedule_data ============== > {schedule_data}")

    holidays_data = [
        {
            "id": str(h.id),
            "name": h.name,
            "fromDate": h.from_date,
            "toDate": h.to_date,
            "isActive": h.is_active,
        }
        for h in office.holidays
    ]

    # ============================
    # SMART ASSIST (GET)
    # ============================
    # smart_assist_data = None

    # if office.smart_assist:
    #     smart_assist_data = {
    #         "enabled": office.smart_assist.enabled,
    #         "items": {
    #             item.key: {
    #                 "enabled": item.enabled,
    #                 "frequency": item.frequency,
    #                 "includeBal": item.include_balance,
    #                 "template": item.template,
    #             }
    #             for item in office.smart_assist.items
    #         }
    #     }

    smart_assist_payload = {
        "enabled": False,
        "items": {}
    }

    if office.smart_assist:
        smart_assist_payload = {
            "enabled": office.smart_assist.enabled,
            "items": office.smart_assist.items or {},
        }


    integrations={
        "eClaims": {
            "vendorType": office.integrations.eclaim_type if office.integrations else None,
            "username": office.integrations.edi_username if office.integrations else None,
            "password": office.integrations.edi_password if office.integrations else None,
        },
        "transworld": {
            "acceleratorAccount": office.transworld.accelerator_account if office.transworld else None,
            "collectionsAccount": office.transworld.collections_account if office.transworld else None,
            "userId": office.transworld.user_id if office.transworld else None,
            "password": office.transworld.password if office.transworld else None,
            "agingDays": office.transworld.aging_days if office.transworld else None,
        },
        "imaging": {
            f"system{img.display_order}": {
                "name": img.system_name,
                "linkType": img.link_type,
                "mode": img.mode,
            }
            for img in office.imaging_systems
        },
        "textMessaging": {
            "phoneNumber": office.integrations.text_phone if office.integrations else None,
            "verified": office.integrations.text_verified if office.integrations else False,
        },
        "patientUrls": {
            "formsUrl": office.patient_urls.forms_url if office.patient_urls else None,
            "schedulingUrl": office.patient_urls.scheduling_url if office.patient_urls else None,
            "financingUrl": office.patient_urls.financing_url if office.patient_urls else None,
            "customUrl1": office.patient_urls.custom_url_1 if office.patient_urls else None,
            "customUrl2": office.patient_urls.custom_url_2 if office.patient_urls else None,
        },
        "acceptedCards": [
            pm.card_type for pm in office.payment_methods if pm.is_active
        ],
    }

    advanced = None
    if office.advanced:
        a = office.advanced
        advanced = {
            "annualFinanceChargePercent": a.annual_finance_charge_percent,
            "minimumBalance": a.minimum_balance,
            "minimumFinanceCharge": a.minimum_finance_charge,
            "daysBeforeFinanceCharge": a.days_before_finance_charge,
            "salesTaxPercent": a.sales_tax_percent,

            "insuranceGroup": a.insurance_group,
            "schedulerEndDate": a.scheduler_end_date,
            "eligibilityThresholdDays": a.eligibility_threshold_days,
            "sendECard": a.send_ecard,

            "defaultPlaceOfService": a.default_place_of_service,
            "defaultAppointmentDuration": a.default_appointment_duration,
            "defaultAreaCode": a.default_area_code,
            "defaultCity": a.default_city,
            "defaultState": a.default_state,
            "defaultZip": a.default_zip,
            "preferredProvider": a.preferred_provider,
            "defaultCoverageType": a.default_coverage_type,
            "isOrthoOffice": a.is_ortho_office,

            "hipaaNotice": a.hipaa_notice,
            "consentForm": a.consent_form,
            "additionalConsentForm": a.additional_consent_form,

            "automatedCampaignsEffectiveDate": a.automated_campaigns_effective_date,
        }





    return OfficePayload(
        officeId=office.id,
        officeName=office.office_name,
        shortId=office.office_code,

        address=Address(
            address1=office.address_line1,
            address2=office.address_line2,
            city=office.city,
            state=office.state,
            zip=office.zip,
            timeZone=office.timezone,
        ),

        contact=Contact(
            phone1=office.phone1,
            phone2=office.phone2,
            phone1Ext=office.phone1ext,
            email=office.email,
        ),

        # billing=Billing(),
        # settings=Settings(isActive=office.is_active),

       

        billing = Billing(
            billingProviderId = other.insurance_billing_providerid if other else None,
            billingProviderName=other.insurance_billing_provider if other else None,
            useBillingLicense=(
                other.billing_license_type == "LICENSED"
                if other and other.billing_license_type else None
            ),
            taxId=other.tax_id if other else None,
            openingDate=other.opening_date if other else None,
            officeGroup=other.office_group if other else None,
            defaultUCRFeeSchedule=other.default_ucr_fee_schedule if other else None,
            defaultFeeSchedule=other.default_fee_schedule if other else None
        ),

        settings = Settings(
            schedulerTimeInterval=other.scheduler_interval_minutes if other else None,
            isActive=office.is_active
        ),
        statementMessages=StatementMessages(
            general = statements.general_message if statements else None,
            current = statements.current_message if statements else None,
            day30 = statements.msg_30_day if statements else None,
            day60 = statements.msg_60_day if statements else None,
            day90 = statements.msg_90_day if statements else None,
            day120 = statements.msg_120_day if statements else None,
        ),

        statementSettings=StatementSettings(
            correspondenceName =  statements.correspondence_name if statements else None,
            statementName = statements.statement_name if statements else None,
            statementAddress = statements.statement_address if statements else None,
            statementPhone = statements.statement_phone if statements else None,
            logoUrl = statements.correspondence_name if statements else None
            ),

        # acceptedCards=[],


        operatories=[
            Operatory(
                id=f"op_{op.id}",
                name=op.name,
                order=op.display_order,
                isActive=op.is_active,
                hasFutureAppointments=op.has_future_appointments,
            )
            for op in office.operatories
        ],

        
       
        schedule=schedule_data,
        # holidays=[],
        holidays=holidays_data,

        smartAssist=smart_assist_payload,#SmartAssist(**smart_assist_data) if smart_assist_data else None,

        advanced=advanced,
        integrations=integrations,
        # smartAssist=SmartAssist(enabled=False, items={}),

        # eClaims=EClaims(),
        # transworld=Transworld(),
        # imaging=Imaging(),
        # textMessaging=TextMessaging(),
        # patientUrls=PatientUrls(),
        
        # Audit fields
        created_by=office.created_by,
        created_date=office.created_at,
        modified_by=office.updated_by,
        modified_at=office.updated_at,
    )


#######################################################################################33

def serialize_smart_items(items: dict) -> dict:
    return {
        key: {
            "enabled": item.enabled,
            "frequency": item.frequency,
            "includeBal": item.includeBal,
            "template": item.template,
        }
        for key, item in items.items()
    }


#####################################################################

def update_office_full(db: Session, payload: OfficePayload, current_user: User):
    office = db.query(Office).filter(Office.id == payload.officeId).first()
    if not office:
        raise HTTPException(status_code=404, detail="Office not found")

    # ==================================================
    # CORE
    # ==================================================
    if payload.officeName is not None:
        office.office_name = payload.officeName

    if payload.shortId is not None:
        office.office_code = payload.shortId

    # ==================================================
    # ADDRESS
    # ==================================================
    if payload.address:
        if payload.address.address1 is not None:
            office.address_line1 = payload.address.address1
        if payload.address.address2 is not None:
            office.address_line2 = payload.address.address2
        if payload.address.city is not None:
            office.city = payload.address.city
        if payload.address.state is not None:
            office.state = payload.address.state
        if payload.address.zip is not None:
            office.zip = payload.address.zip
        if payload.address.timeZone is not None:
            office.timezone = payload.address.timeZone

    # ==================================================
    # CONTACT
    # ==================================================
    if payload.contact:
        if payload.contact.phone1 is not None:
            office.phone1 = payload.contact.phone1
        if payload.contact.phone2 is not None:
            office.phone2 = payload.contact.phone2
        if payload.contact.phone1Ext is not None:
            office.phone1ext = payload.contact.phone1Ext
        if payload.contact.email is not None:
            office.email = payload.contact.email

    # ==================================================
    # ENSURE other_info EXISTS (SAFE)
    # ==================================================
    other = office.other_info

    if payload.billing or payload.settings:
        if not other:
            other = OfficeOtherInfo(office_id=office.id)
            office.other_info = other

    # ==================================================
    # BILLING (PATCH SAFE – NO DATA LOSS)
    # ==================================================
    if payload.billing and other:
        if payload.billing.taxId is not None:
            other.tax_id = payload.billing.taxId

        if payload.billing.billingProviderId is not None:
            other.insurance_billing_providerid = payload.billing.billingProviderId

        if payload.billing.billingProviderName is not None:
            other.insurance_billing_provider = payload.billing.billingProviderName

        if payload.billing.officeGroup is not None:
            other.office_group = payload.billing.officeGroup

        if payload.billing.defaultUCRFeeSchedule is not None:
            other.default_ucr_fee_schedule = payload.billing.defaultUCRFeeSchedule

        if payload.billing.defaultFeeSchedule is not None:
            other.default_fee_schedule = payload.billing.defaultFeeSchedule

        if payload.billing.openingDate is not None:
            other.opening_date = payload.billing.openingDate

        if payload.billing.useBillingLicense is not None:
            other.billing_license_type = (
                "LICENSED"
                if payload.billing.useBillingLicense
                else "UNLICENSED"
            )

    # ==================================================
    # SETTINGS
    # ==================================================
    if payload.settings:
        if payload.settings.schedulerTimeInterval is not None and other:
            other.scheduler_interval_minutes = (
                payload.settings.schedulerTimeInterval
            )

        if payload.settings.isActive is not None:
            office.is_active = payload.settings.isActive

    statements = office.statements

    if payload.statementMessages and statements:
        if payload.statementMessages.general:
            statements.general_message = payload.statementMessages.general
        if payload.statementMessages.current:
            statements.current_message = payload.statementMessages.current        
        if payload.statementMessages.day30:
            statements.msg_30_day = payload.statementMessages.day30

        if payload.statementMessages.day60:
            statements.msg_60_day = payload.statementMessages.day60

        if payload.statementMessages.day90:
            statements.msg_90_day = payload.statementMessages.day90

        if payload.statementMessages.day120:
            statements.msg_120_day = payload.statementMessages.day120

    if payload.statementSettings and statements:
        if payload.statementSettings.correspondenceName:
            statements.correspondence_name = payload.statementSettings.correspondenceName
        if payload.statementSettings.statementName:
            statements.statement_name = payload.statementSettings.statementName
        if payload.statementSettings.statementAddress:
            statements.statement_address = payload.statementSettings.statementAddress
        if payload.statementSettings.statementPhone:
            statements.statement_phone = payload.statementSettings.statementPhone
        if payload.statementSettings.logoUrl:
            statements.logo_url = payload.statementSettings.logoUrl



        # eclaim_type = Column(String(50))
    
    
    

    # ==================================================
    # OPERATORIES (TRANSACTION SAFE REPLACE)
    # ==================================================
    if payload.operatories is not None:
        try:
            with db.begin_nested():
                db.query(OfficeOperatory).filter(
                    OfficeOperatory.office_id == office.id
                ).delete()

                for op in payload.operatories:
                    db.add(
                        OfficeOperatory(
                            office_id=office.id,
                            name=op.name,
                            display_order=op.order,
                            is_active=op.isActive,
                            has_future_appointments=op.hasFutureAppointments,
                        )
                    )
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Failed to update operatories: {str(exc)}",
            )

    # schedules = office.schedules


    # if payload.schedule is not None and isinstance(payload.schedule, dict):

    #     for day_name, day_data in payload.schedule.items():
    #         if not day_data:
    #             continue

    #         schedules.day_of_week = day_name.lower()

    #         logger.info(f"schedules.day_of_week  {schedules.day_of_week}")

    #         if day_data.start not in (None, ""):
    #             schedules.start_time = day_data.start

    #             logger.info(f"day_data.start  {day_data.start}")

    #         if day_data.end not in (None, ""):
    #             schedules.end_time = day_data.end
    #             logger.info(f"day_data.end  {day_data.end}")

    #         if day_data.lunchStart not in (None, ""):
    #             schedules.lunch_start = day_data.lunchStart

    #             logger.info(f"day_data.lunchStart  {day_data.lunchStart}")

    #         if day_data.lunchEnd not in (None, ""):
    #             schedules.lunch_end = day_data.lunchEnd

    #             logger.info(f"day_data.lunchEnd  {day_data.lunchEnd}")

    #         # closed can be False → must check explicitly
    #         if day_data.closed is not None:
    #             schedules.is_closed = day_data.closed

    #             logger.info(f"day_data.closed  {day_data.closed}")

    # from sqlalchemy.orm.exc import NoResultFound

    if payload.schedule and isinstance(payload.schedule, dict):

        for day_name, day_data in payload.schedule.items():
            if not day_data:
                continue

            day = day_name.lower()

            #  Find existing schedule row for this day
            schedule_row = (
                db.query(OfficeSchedule)
                .filter(
                    OfficeSchedule.office_id == office.id,
                    OfficeSchedule.day_of_week == day
                )
                .one_or_none()
            )

            # ➕ Create if not exists
            if not schedule_row:
                schedule_row = OfficeSchedule(
                    office_id=office.id,
                    day_of_week=day
                )
                db.add(schedule_row)

            #  Update fields (PATCH-safe)
            if day_data.start not in (None, ""):
                schedule_row.start_time = day_data.start

            if day_data.end not in (None, ""):
                schedule_row.end_time = day_data.end

            if day_data.lunchStart not in (None, ""):
                schedule_row.lunch_start = day_data.lunchStart

            if day_data.lunchEnd not in (None, ""):
                schedule_row.lunch_end = day_data.lunchEnd

            # closed can be False → must check explicitly
            if day_data.closed is not None:
                schedule_row.is_closed = day_data.closed

    
    # ==================================================
    # HOLIDAYS (SAFE REPLACE)
    # ==================================================
    if payload.holidays is not None:
        try:
            with db.begin_nested():
                # delete existing holidays
                db.query(OfficeHoliday).filter(
                    OfficeHoliday.office_id == office.id
                ).delete()

                for h in payload.holidays:
                    db.add(
                        OfficeHoliday(
                            office_id=office.id,
                            name=h.name,
                            from_date=h.fromDate,
                            to_date=h.toDate,
                            is_active=h.isActive,
                        )
                    )
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Failed to update holidays: {str(exc)}",
            )

    
    # ============================
    # SMART ASSIST (UPSERT)
    # ============================
    # if payload.smartAssist is not None:

    #     smart = office.smart_assist

    #     # Create parent row if missing
    #     if not smart:
    #         smart = OfficeSmartAssist(
    #             office_id=office.id,
    #             enabled=payload.smartAssist.enabled
    #         )
    #         office.smart_assist = smart
    #         db.add(smart)
    #     else:
    #         smart.enabled = payload.smartAssist.enabled

    #     # Replace items safely
    #     if payload.smartAssist.items is not None:
    #         db.query(OfficeSmartAssistItem).filter(
    #             OfficeSmartAssistItem.smart_assist_id == smart.id
    #         ).delete()

    #         for key, item in payload.smartAssist.items.items():
    #             db.add(
    #                 OfficeSmartAssistItem(
    #                     smart_assist_id=smart.id,
    #                     key=key,
    #                     enabled=item.enabled,
    #                     frequency=item.frequency,
    #                     include_balance=item.includeBal,
    #                     template=item.template,
    #                 )
    #             )

    # if payload.smartAssist:
    #     smart = office.smart_assist

    #     # Create if missing
    #     if not smart:
    #         smart = OfficeSmartAssist(
    #             office_id=office.id
    #         )
    #         office.smart_assist = smart

    #     # Patch-safe updates
    #     if payload.smartAssist.enabled is not None:
    #         smart.enabled = payload.smartAssist.enabled

    #     if payload.smartAssist.items is not None:
    #         smart.items = payload.smartAssist.items

    if payload.smartAssist:
        smart = office.smart_assist or OfficeSmartAssist(
            office_id=office.id
        )

        smart.enabled = payload.smartAssist.enabled
        # smart.items = serialize_smart_items(
        #     payload.smartAssist.items or {}
        # )

        smart.items = {
            k: v.model_dump()
            for k, v in payload.smartAssist.items.items()
        }



        office.smart_assist = smart

    if payload.integrations:
        integ = office.integrations or OfficeIntegrations(office_id=office.id)
        office.integrations = integ

        if payload.integrations.eClaims:
            integ.eclaim_type = payload.integrations.eClaims.vendorType
            integ.edi_username = payload.integrations.eClaims.username
            integ.edi_password = payload.integrations.eClaims.password

        if payload.integrations.textMessaging:
            integ.text_phone = payload.integrations.textMessaging.phoneNumber
            integ.text_verified = payload.integrations.textMessaging.verified

    # if payload.integrations and payload.integrations.imaging:
    #     db.query(OfficeImagingSystem).filter(
    #         OfficeImagingSystem.office_id == office.id
    #     ).delete()

    #     # for key, val in payload.integrations.imaging.items():
    #     #     order = int(key.replace("system", ""))
    #     #     db.add(
    #     #         OfficeImagingSystem(
    #     #             office_id=office.id,
    #     #             system_name=val.name,
    #     #             link_type=val.linkType,
    #     #             mode=val.mode,
    #     #             display_order=order,
    #     #         )
    #     #     )
    #     imaging = payload.integrations.imaging

    #     systems = [
    #         ("system1", imaging.system1),
    #         ("system2", imaging.system2),
    #         ("system3", imaging.system3),
    #     ]

    #     for key, system in systems:
    #         if not system:
    #             continue

    #         display_order = int(key.replace("system", ""))

    #         db.add(
    #             OfficeImagingSystem(
    #                 office_id=office.id,
    #                 system_name=system.name,
    #                 link_type=system.linkType,
    #                 mode=system.mode,
    #                 display_order=display_order,
    #             )
    #         )

    # ==================================================
    # IMAGING SYSTEMS (SAFE REPLACE)
    # ==================================================
    if payload.integrations and payload.integrations.imaging:

        db.query(OfficeImagingSystem).filter(
            OfficeImagingSystem.office_id == office.id
        ).delete()

        imaging_dict = payload.integrations.imaging.model_dump(exclude_none=True)

        for key, val in imaging_dict.items():
            display_order = int(key.replace("system", ""))

            db.add(
                OfficeImagingSystem(
                    office_id=office.id,
                    system_name=val.get("name"),
                    link_type=val.get("linkType"),
                    mode=val.get("mode"),
                    display_order=display_order,
                )
            )



    
    if payload.integrations and payload.integrations.patientUrls:
        urls = office.patient_urls or OfficePatientUrls(office_id=office.id)
        office.patient_urls = urls

        urls.forms_url = payload.integrations.patientUrls.formsUrl
        urls.scheduling_url = payload.integrations.patientUrls.schedulingUrl
        urls.financing_url = payload.integrations.patientUrls.financingUrl
        urls.custom_url_1 = payload.integrations.patientUrls.customUrl1
        urls.custom_url_2 = payload.integrations.patientUrls.customUrl2

    if payload.integrations and payload.integrations.acceptedCards is not None:
        db.query(OfficePaymentMethod).filter(
            OfficePaymentMethod.office_id == office.id
        ).delete()

        for card in payload.integrations.acceptedCards:
            db.add(
                OfficePaymentMethod(
                    office_id=office.id,
                    card_type=card,
                    is_active=True,
                )
            )
    # ==================================================
    # TRANSWORLD (UPSERT / SAFE UPDATE)
    # ==================================================
    if payload.integrations and payload.integrations.transworld:

        tw_payload = payload.integrations.transworld

        transworld = office.transworld or OfficeTransworld(
            office_id=office.id
        )
        office.transworld = transworld

        transworld.accelerator_account = tw_payload.acceleratorAccount
        transworld.collections_account = tw_payload.collectionsAccount
        transworld.user_id = tw_payload.userId
        transworld.password = tw_payload.password
        transworld.aging_days = tw_payload.agingDays

    elif payload.integrations and payload.integrations.transworld is None:
        if office.transworld:
            db.delete(office.transworld)


    # ==================================================
    # ADVANCED SETTINGS (UPSERT)
    # ==================================================
    if payload.advanced:

        adv = office.advanced or OfficeAdvancedSettings(
            office_id=office.id
        )
        office.advanced = adv

        a = payload.advanced

        adv.annual_finance_charge_percent = a.annualFinanceChargePercent
        adv.minimum_balance = a.minimumBalance
        adv.minimum_finance_charge = a.minimumFinanceCharge
        adv.days_before_finance_charge = a.daysBeforeFinanceCharge
        adv.sales_tax_percent = a.salesTaxPercent

        adv.insurance_group = a.insuranceGroup
        adv.scheduler_end_date = a.schedulerEndDate
        adv.eligibility_threshold_days = a.eligibilityThresholdDays
        adv.send_ecard = a.sendECard

        adv.default_place_of_service = a.defaultPlaceOfService
        adv.default_appointment_duration = a.defaultAppointmentDuration
        adv.default_area_code = a.defaultAreaCode
        adv.default_city = a.defaultCity
        adv.default_state = a.defaultState
        adv.default_zip = a.defaultZip
        adv.preferred_provider = a.preferredProvider
        adv.default_coverage_type = a.defaultCoverageType
        adv.is_ortho_office = a.isOrthoOffice

        adv.hipaa_notice = a.hipaaNotice
        adv.consent_form = a.consentForm
        adv.additional_consent_form = a.additionalConsentForm

        adv.automated_campaigns_effective_date = a.automatedCampaignsEffectiveDate



    # ==================================================
    # UPDATE AUDIT FIELDS
    # ==================================================
    from datetime import datetime
    office.updated_by = current_user.username if current_user else None
    office.updated_at = datetime.utcnow()
    
    # ==================================================
    # COMMIT & RETURN
    # ==================================================
    logger.info(f"office ===============+++++++++++++> {office}")
    db.commit()
    db.refresh(office)
    db.commit()

    return get_office_full(db, office.id, current_user)



#####################################################################
def create_office_full(db: Session, payload, current_user: User):

    # ==================================================
    # VALIDATION
    # ==================================================
    if db.query(Office).filter(Office.id == payload.officeId).first():
        raise HTTPException(
            status_code=400,
            detail="Office with this ID already exists"
        )

    # ==================================================
    # CORE OFFICE
    # ==================================================
    office = Office(
        # id=payload.officeId,
        tenant_id=1,
        office_name=payload.officeName,
        office_code=payload.shortId,
        address_line1=payload.address.address1 if payload.address else None,
        address_line2=payload.address.address2 if payload.address else None,
        city=payload.address.city if payload.address else None,
        state=payload.address.state if payload.address else None,
        zip=payload.address.zip if payload.address else None,
        timezone=payload.address.timeZone if payload.address else None,
        phone1=payload.contact.phone1 if payload.contact else None,
        phone2=payload.contact.phone2 if payload.contact else None,
        phone1ext=payload.contact.phone1Ext if payload.contact else None,
        email=payload.contact.email if payload.contact else None,
        is_active=payload.settings.isActive if payload.settings else True,
        created_by=current_user.username if current_user else "system",
    )

    db.add(office)
    db.flush()  # 🔑 office.id available

    # ==================================================
    # OTHER INFO (BILLING + SETTINGS)
    # ==================================================
    if payload.billing or payload.settings:
        other = OfficeOtherInfo(
            office_id=office.id,
            tax_id=payload.billing.taxId if payload.billing else None,
            insurance_billing_providerid=payload.billing.billingProviderId if payload.billing else None,
            insurance_billing_provider=payload.billing.billingProviderName if payload.billing else None,
            office_group=payload.billing.officeGroup if payload.billing else None,
            default_ucr_fee_schedule=payload.billing.defaultUCRFeeSchedule if payload.billing else None,
            default_fee_schedule=payload.billing.defaultFeeSchedule if payload.billing else None,
            opening_date=payload.billing.openingDate if payload.billing else None,
            billing_license_type=(
                "LICENSED"
                if payload.billing and payload.billing.useBillingLicense
                else "UNLICENSED"
            ),
            scheduler_interval_minutes=(
                payload.settings.schedulerTimeInterval
                if payload.settings else None
            ),
        )
        office.other_info = other
        db.add(other)

    # ==================================================
    # STATEMENTS (SINGLE TABLE)
    # ==================================================
    if payload.statementMessages or payload.statementSettings:
        statements = OfficeStatement(
            office_id=office.id,
            general_message=payload.statementMessages.general if payload.statementMessages else None,
            current_message=payload.statementMessages.current if payload.statementMessages else None,
            msg_30_day=payload.statementMessages.day30 if payload.statementMessages else None,
            msg_60_day=payload.statementMessages.day60 if payload.statementMessages else None,
            msg_90_day=payload.statementMessages.day90 if payload.statementMessages else None,
            msg_120_day=payload.statementMessages.day120 if payload.statementMessages else None,
            correspondence_name=payload.statementSettings.correspondenceName if payload.statementSettings else None,
            statement_name=payload.statementSettings.statementName if payload.statementSettings else None,
            statement_address=payload.statementSettings.statementAddress if payload.statementSettings else None,
            statement_phone=payload.statementSettings.statementPhone if payload.statementSettings else None,
            logo_url=payload.statementSettings.logoUrl if payload.statementSettings else None,
        )
        office.statements = statements
        db.add(statements)

    # ==================================================
    # OPERATORIES
    # ==================================================
    for op in payload.operatories or []:
        db.add(
            OfficeOperatory(
                office_id=office.id,
                name=op.name,
                display_order=op.order,
                is_active=op.isActive,
                has_future_appointments=op.hasFutureAppointments,
            )
        )

    # ==================================================
    # SCHEDULE
    # ==================================================
    for day, data in (payload.schedule or {}).items():
        if not data:
            continue

        db.add(
            OfficeSchedule(
                office_id=office.id,
                day_of_week=day.lower(),
                start_time=data.start,
                end_time=data.end,
                lunch_start=data.lunchStart,
                lunch_end=data.lunchEnd,
                is_closed=data.closed,
            )
        )

    # ==================================================
    # HOLIDAYS (CREATE – SAFE)
    # ==================================================
    for h in payload.holidays or []:
        if not h.fromDate or not h.toDate:
            continue

        db.add(
            OfficeHoliday(
                office_id=office.id,
                name=h.name,
                from_date=h.fromDate,
                to_date=h.toDate,
                is_active=h.isActive,
            )
        )

    # ==================================================
    # INTEGRATIONS
    # ==================================================
    if payload.integrations:
        integ = OfficeIntegrations(office_id=office.id)
        office.integrations = integ
        db.add(integ)

        if payload.integrations.eClaims:
            integ.eclaim_type = payload.integrations.eClaims.vendorType
            integ.edi_username = payload.integrations.eClaims.username
            integ.edi_password = payload.integrations.eClaims.password

        if payload.integrations.textMessaging:
            integ.text_phone = payload.integrations.textMessaging.phoneNumber
            integ.text_verified = payload.integrations.textMessaging.verified

        if payload.integrations.transworld:
            db.add(
                OfficeTransworld(
                    office_id=office.id,
                    accelerator_account=payload.integrations.transworld.acceleratorAccount,
                    collections_account=payload.integrations.transworld.collectionsAccount,
                    user_id=payload.integrations.transworld.userId,
                    password=payload.integrations.transworld.password,
                    aging_days=payload.integrations.transworld.agingDays,
                )
            )

        if payload.integrations.patientUrls:
            db.add(
                OfficePatientUrls(
                    office_id=office.id,
                    forms_url=payload.integrations.patientUrls.formsUrl,
                    scheduling_url=payload.integrations.patientUrls.schedulingUrl,
                    financing_url=payload.integrations.patientUrls.financingUrl,
                    custom_url_1=payload.integrations.patientUrls.customUrl1,
                    custom_url_2=payload.integrations.patientUrls.customUrl2,
                )
            )

        for card in payload.integrations.acceptedCards or []:
            db.add(
                OfficePaymentMethod(
                    office_id=office.id,
                    card_type=card,
                    is_active=True,
                )
            )

        if payload.integrations.imaging:
            imaging_dict = payload.integrations.imaging.model_dump(exclude_none=True)
            for key, val in imaging_dict.items():
                display_order = int(key.replace("system", ""))
                db.add(
                    OfficeImagingSystem(
                        office_id=office.id,
                        system_name=val.get("name"),
                        link_type=val.get("linkType"),
                        mode=val.get("mode"),
                        display_order=display_order,
                    )
                )

    # ==================================================
    # SMART ASSIST (CREATE)
    # ==================================================
    if payload.smartAssist:
        smart = OfficeSmartAssist(
            office_id=office.id,
            enabled=payload.smartAssist.enabled,
            items={
                k: v.model_dump()
                for k, v in payload.smartAssist.items.items()
            } if payload.smartAssist.items else {},
        )
        office.smart_assist = smart
        db.add(smart)

    # ==================================================
    # ADVANCED
    # ==================================================
    if payload.advanced:
        adv = OfficeAdvancedSettings(
            office_id=office.id,
            annual_finance_charge_percent=payload.advanced.annualFinanceChargePercent,
            minimum_balance=payload.advanced.minimumBalance,
            minimum_finance_charge=payload.advanced.minimumFinanceCharge,
            days_before_finance_charge=payload.advanced.daysBeforeFinanceCharge,
            sales_tax_percent=payload.advanced.salesTaxPercent,
            insurance_group=payload.advanced.insuranceGroup,
            scheduler_end_date=payload.advanced.schedulerEndDate,
            eligibility_threshold_days=payload.advanced.eligibilityThresholdDays,
            send_ecard=payload.advanced.sendECard,
            default_place_of_service=payload.advanced.defaultPlaceOfService,
            default_appointment_duration=payload.advanced.defaultAppointmentDuration,
            default_area_code=payload.advanced.defaultAreaCode,
            default_city=payload.advanced.defaultCity,
            default_state=payload.advanced.defaultState,
            default_zip=payload.advanced.defaultZip,
            preferred_provider=payload.advanced.preferredProvider,
            default_coverage_type=payload.advanced.defaultCoverageType,
            is_ortho_office=payload.advanced.isOrthoOffice,
            hipaa_notice=payload.advanced.hipaaNotice,
            consent_form=payload.advanced.consentForm,
            additional_consent_form=payload.advanced.additionalConsentForm,
            automated_campaigns_effective_date=payload.advanced.automatedCampaignsEffectiveDate,
        )
        db.add(adv)

    # ==================================================
    # COMMIT & RETURN
    # ==================================================
    db.commit()
    return get_office_full(db, office.id, current_user)

# ############################################################################
# # app/api/v1/offices/services/billing_provider.py



def create_billing_provider(
    db: Session,
    payload: BillingProviderCreate
) -> BillingProviderResponse:

    existing = db.query(BillingProvider).filter(
        BillingProvider.name == payload.name
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Billing provider already exists"
        )

    provider = BillingProvider(
        name=payload.name,
        npi=payload.npi,
        license=payload.license
    )

    db.add(provider)
    db.commit()
    db.refresh(provider)

    return BillingProviderResponse(
        id=provider.id,
        name=provider.name
    )

# app/api/v1/offices/services/fee_schedule.py




def create_fee_schedule(
    db: Session,
    payload: FeeScheduleCreate
) -> FeeScheduleResponse:

    exists = db.query(FeeSchedule).filter(
        FeeSchedule.name == payload.name,
        FeeSchedule.type == payload.type
    ).first()

    if exists:
        raise HTTPException(409, "Fee schedule already exists")

    fs = FeeSchedule(
        name=payload.name,
        type=payload.type
    )

    db.add(fs)
    db.commit()
    db.refresh(fs)

    return FeeScheduleResponse(
        id=fs.id,
        name=fs.name,
        type=fs.type
    )




def get_office_metadata(db: Session) -> OfficeMetadataResponse:
    # --------------------------------------------------
    # TIME ZONES (POSTGRES SYSTEM TABLE)
    # --------------------------------------------------
    time_zones = [
        row[0]
        for row in db.execute(
            text("""
                SELECT name
                FROM pg_timezone_names
                WHERE name LIKE '%/%'
                ORDER BY name
            """)
        ).fetchall()
    ]

    # --------------------------------------------------
    # BILLING PROVIDERS (FROM billing_providers TABLE)
    # --------------------------------------------------
    billing_providers = [
        BillingProviderMeta(
            id=str(provider.id),
            name=provider.name,
        )
        for provider in db.query(BillingProvider)
        .order_by(BillingProvider.name)
        .all()
    ]

    # --------------------------------------------------
    # FEE SCHEDULES (FROM fee_schedules TABLE)
    # --------------------------------------------------
    fee_schedules = [
        FeeScheduleMeta(
            id=str(schedule.id),
            name=schedule.name,
            type=schedule.type,  # "UCR" | "STANDARD"
        )
        for schedule in db.query(FeeSchedule)
        .order_by(FeeSchedule.name)
        .all()
    ]

    # --------------------------------------------------
    # RESPONSE
    # --------------------------------------------------
    return OfficeMetadataResponse(
        time_zones=time_zones,
        billing_providers=billing_providers,
        fee_schedules=fee_schedules,
    )
