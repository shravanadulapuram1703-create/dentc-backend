################################################################################################################

from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from sqlalchemy import text
from app.models.offices import Office

from app.api.v1.offices.service  import (get_office_full, 
                                        create_billing_provider,
                                        update_office_full,
                                        get_office_metadata,
                                        create_fee_schedule,
                                        create_office_full)

from app.api.v1.offices.schemas import (OfficePayload,
                                        # PatientUrls,
                                        # TextMessaging,
                                        # Imaging,
                                        # ImagingSystem,
                                        # Transworld,
                                        # EClaims,
                                        Integrations,
                                        SmartAssist,
                                        SmartAssistItem,
                                        Holiday,
                                        DaySchedule,
                                        Operatory,
                                        StatementSettings,
                                        StatementMessages,
                                        Settings,
                                        Billing,
                                        Contact,
                                        Address,
                                        OfficeMetadataResponse,
                                        BillingProviderMeta,
                                        FeeScheduleMeta,
                                        BillingProviderResponse,
                                        BillingProviderCreate,
                                        FeeScheduleCreate,
                                        FeeScheduleResponse,
                                        OfficeAdvancedResponse,
                                        OfficeAdvancedPayload,
                                        CreateOfficePayload)

import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/offices",
    tags=["Offices Setup"]
)



@router.get("/")
def get_offices_list(db: Session = Depends(get_db)):
    offices = db.query(Office).order_by(Office.id).all()

    return [
        {
            "id": f"off-{office.id:03d}",     # UI-friendly ID (off-001)
            "officeId": office.id,            # DB ID
            "officeName": office.office_name,
            "shortId": office.office_code,
            "city": office.city,
            "state": office.state,
            "phone1": office.phone1,
            "isActive": office.is_active
        }
        for office in offices
    ]



@router.get("/{office_id}/setup", response_model=OfficePayload)
def get_office(office_id: int, db: Session = Depends(get_db)):
    return get_office_full(db, office_id)

@router.put("/{office_id}", response_model=OfficePayload)
def update_office(
    office_id: int,
    payload: OfficePayload,
    db: Session = Depends(get_db)
):
    payload.officeId = office_id
    return update_office_full(db, payload)

# @router.post("", include_in_schema=False)
@router.post("/", response_model=OfficePayload)
def create_office(
    payload: CreateOfficePayload,
    db: Session = Depends(get_db)
):
    return create_office_full(db, payload)





@router.get("/next-id")
def get_next_office_id(db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            SELECT CASE
                WHEN is_called THEN last_value + 1
                ELSE last_value
            END
            FROM public.offices_id_seq
        """)
    ).scalar_one()

    return {
        "nextOfficeId": result
    }




@router.get(
    "/metadata",
    response_model=OfficeMetadataResponse
)
def office_metadata(db: Session = Depends(get_db)):
    return get_office_metadata(db)




@router.post(
    "/billing-providers",
    response_model=BillingProviderResponse,
    status_code=201
)
def add_billing_provider(
    payload: BillingProviderCreate,
    db: Session = Depends(get_db)
):
    return create_billing_provider(db, payload)



@router.post(
    "/fee-schedules",
    response_model=FeeScheduleResponse,
    status_code=201
)
def add_fee_schedule(
    payload: FeeScheduleCreate,
    db: Session = Depends(get_db)
):
    return create_fee_schedule(db, payload)





#################################################################################################

# @router.get("/metadata")
# def get_office_metadata(db: Session = Depends(get_db)):
#     # ---- Time Zones (system-driven, always current)
#     time_zones = pytz.common_timezones

#     # ---- Billing Providers (DB)
#     billing_providers = [
#         {
#             "id": str(p.id),
#             "name": p.name,
#             "npi": p.npi,
#             "license": p.license
#         }
#         for p in db.query(BillingProvider)
#         .filter(BillingProvider.is_active == True)
#         .order_by(BillingProvider.name)
#         .all()
#     ]

#     # ---- Fee Schedules (DB)
#     fee_schedules = [
#         {
#             "id": str(f.id),
#             "name": f.name,
#             "type": f.type
#         }
#         for f in db.query(FeeSchedule)
#         .filter(FeeSchedule.is_active == True)
#         .order_by(FeeSchedule.name)
#         .all()
#     ]

#     return {
#         "time_zones": time_zones,
#         "billing_providers": billing_providers,
#         "fee_schedules": fee_schedules
#     }




######################################################################################################



# @router.get("/{office_id}/setup")
# def office_setup():
#     out = {
#             "office": {
#                 "officeId": 1001,
#                 "officeName": "Main Street Dental",
#                 "shortId": "MSD",
#                 "address1": "123 Main Street",
#                 "address2": "Suite 200",
#                 "city": "San Francisco",
#                 "state": "CA",
#                 "zip": "94102",
#                 "timeZone": "America/Los_Angeles",
#                 "phone1": "(415) 555-1234",
#                 "phone1Ext": "100",
#                 "phone2":"9291",
#                 "email": "contact@mainstreetdental.com",
#                 "billingProviderId": "prov-001",
#                 "billingProviderName": "Dr. Sarah Johnson",
#                 "useBillingLicense": True,
#                 "taxId": "94-1234567",
#                 "openingDate": "2020-01-15",
#                 "officeGroup":"Bay Area Group 1",
#                 "defaultUCRFeeSchedule": "UCR California 2024",
#                 "defaultFeeSchedule": "Standard Fee Schedule",
#                 "schedulerTimeInterval": 5,
#                 "isActive": True
#             },
#             "statement": {
#                "statement_messages": {
#                                     "general": "Thank you for choosing our practice",
#                                     "current": "Payment due upon receipt",
#                                     "day30": "Your account is 30 days past due",
#                                     "day60": "Your account is 60 days past due",
#                                     "day90": "Final notice before collections",
#                                     "day120": "Account sent to collections"
#                                     },
#                 "statement_settings": {
#                                     "correspondence_name": "Main Street Dental",
#                                     "statement_name": "Main Street Dental",
#                                     "statement_address": "123 Main St, SF, CA 94102",
#                                     "statement_phone": "(415) 555-1234",
#                                     "logo_url": "https://cdn.example.com/logos/offices/1001.png"
#                                     }
#             },
#             "integration": {
#                             "eClaims": {
#                             "vendorType": "ClaimConnect",
#                             "username": "mainstreet_claims",
#                             "password": "encrypted_password_here"
#                             },
#                             "transworld": {
#                             "acceleratorAccount": "TWC-ACC-10293",
#                             "collectionsAccount": "TWC-COLL-55821",
#                             "userId": "msd_collections",
#                             "password": "encrypted_password_here",
#                             "agingDays": 90
#                             },
#                             "imaging": {
#                             "system1": {
#                                 "name": "Dexis",
#                                 "linkType": "Chart Number",
#                                 "mode": "Default"
#                             },
#                             "system2": {
#                                 "name": "Carestream",
#                                 "linkType": "Patient ID",
#                                 "mode": "Default"
#                             },
#                             "system3": {
#                                 "name": "XVWeb",
#                                 "linkType": "Account Number",
#                                 "mode": "Custom"
#                             }
#                             },

#                             "textMessaging": {
#                             "phoneNumber": "+14155551234",
#                             "verified": True
#                             },

#                             "patientUrls": {
#                             "formsUrl": "https://mainstreetdental.com/forms",
#                             "schedulingUrl": "https://mainstreetdental.com/schedule",
#                             "financingUrl": "https://mainstreetdental.com/financing",
#                             "customUrl1": "https://mainstreetdental.com/new-patients",
#                             "customUrl2": "https://mainstreetdental.com/promotions"
#                             },

#                             "acceptedCards": [
#                             "Visa",
#                             "Mastercard",
#                             "American Express",
#                             "Discover"
#                             ]
#                         },
#             "operatories": [{
#                             "id": "op_1",
#                             "name": "OP 1",
#                             "order": 1,
#                             "is_active": True,
#                             "has_future_appointments": False
#                             },
#                             {
#                             "id": "op_2",
#                             "name": "Hygiene 1",
#                             "order": 2,
#                             "is_active": True,
#                             "has_future_appointments": True
#                             }],
#             "schedule": {"timezone": "America/Los_Angeles",
#                         "week": {
#                             "monday": {
#                             "start": "08:00",
#                             "end": "17:00",
#                             "lunch_start": "12:00",
#                             "lunch_end": "13:00",
#                             "closed": False
#                             },
#                             "tuesday": { "...": "..." },
#                             "wednesday": { "...": "..." },
#                             "thursday": { "...": "..." },
#                             "friday": { "...": "..." },
#                             "saturday": { "closed": True },
#                             "sunday": { "closed": True }
#                         } },
#             "holidays": [{
#                         "id": "hol_1",
#                         "name": "New Year's Day",
#                         "start_date": "2026-01-01",
#                         "end_date": "2026-01-01",
#                         "is_active": True
#                         },
#                         {
#                         "id": "hol_2",
#                         "name": "Thanksgiving",
#                         "start_date": "2026-11-26",
#                         "end_date": "2026-11-27",
#                         "is_active": True
#                         }],
#             "advanced": {   "financial": {
#                                             "annual_finance_charge_percent": 18.0,
#                                             "minimum_balance": 50.0,
#                                             "minimum_finance_charge": 2.0,
#                                             "days_before_finance_charge": 30,
#                                             "sales_tax_percent": 8.5
#                                         },
#                             "scheduler": {
#                                             "end_date": "2026-12-31",
#                                             "default_appointment_duration": 60
#                                         },
#                             "insurance": {
#                                             "insurance_group": "PPO Network A",
#                                             "eligibility_threshold_days": 30,
#                                             "default_coverage_type": "PPO"
#                                         },
#                             "defaults": {
#                                             "place_of_service": "Office",
#                                             "area_code": "415",
#                                             "city": "San Francisco",
#                                             "state": "CA",
#                                             "zip": "94102",
#                                             "preferred_provider_id": "prov_001",
#                                             "is_ortho_office": False
#                                         },
#                             "patient_checkin": {
#                                             "hipaa_notice": True,
#                                             "consent_form": True,
#                                             "additional_consent_form": False
#                                         },
#                             "automation": {
#                                             "send_ecard": False,
#                                             "effective_date": "2026-01-01"
#                                         }
#                                         },
#             "smartAssist": {
#                             "enabled": True,
#                             "items": {
#                                 "payment": {
#                                 "enabled": True,
#                                 "frequency": "Every Visit",
#                                 "includeBal": True
#                                 },
#                                 "email": {
#                                 "enabled": True,
#                                 "frequency": "Every Year"
#                                 },
#                                 "cellPhone": {
#                                 "enabled": False
#                                 },
#                                 "eligibility": {
#                                 "enabled": True,
#                                 "frequency": "Every Visit"
#                                 },
#                                 "medicalHistory": {
#                                 "enabled": True,
#                                 "frequency": "Every Year",
#                                 "template": "Standard Medical History"
#                                 },
#                                 "hipaa": {
#                                 "enabled": True,
#                                 "template": "HIPAA Consent 2024"
#                                 },
#                                 "consentForm1": {
#                                 "enabled": True,
#                                 "template": "Treatment Consent"
#                                 },
#                                 "progressNotes": {
#                                 "enabled": True,
#                                 "frequency": "Every Visit",
                                
#                                 },
#                                 "ledgerPosting": {
#                                 "enabled": True,
#                                 "frequency": "Every Visit",
#                                                                }
#                             }
#                             }

#             }

#     return out

# @router.get("/")
# def office_setup_1():
#     out = [
#             {
#                 "id": "off-001",
#                 "officeId": 1001,
#                 "officeName": "Main Street Dental",
#                 "shortId": "MSD",
#                 "city": "San Francisco",
#                 "state": "CA",
#                 "phone1": "(415) 555-1234",
#                 "isActive": True
#             }
#             ]


#     return out



# @router.put("/{id}")
# async def office_setup_1(id: str, request: Request):
#     payload = await request.json()
#     logger.info(f"Payload received: {payload}")


#     # logger.info("payload :---------------->",payload)
#     out = [
#             {
#                 "id": "off-001",
#                 "officeId": 1001,
#                 "officeName": "Main Street Dental",
#                 "shortId": "MSD",
#                 "city": "San Francisco",
#                 "state": "CA",
#                 "phone1": "(415) 555-1234",
#                 "isActive": True
#             }
#             ]


#     return out



########################################################################################################
# from fastapi import APIRouter, Depends, HTTPException, status
# from sqlalchemy.orm import Session
# from typing import List

# from app.core.database import get_db

# from app.api.v1.offices.schemas import (
#         OfficeCreate,
#         OfficeUpdate,
#         OfficeResponse,
#         OfficeStatementBase,
#         OfficeStatementUpdate,
#         OfficeStatementResponse,
#         OfficeIntegrationBase,
#         OfficeIntegrationCreate,
#         OfficeIntegrationResponse,
#         OfficeScheduleDay,
#         OfficeScheduleUpdate,
#         OfficeScheduleResponse,
#         OfficeHolidayCreate,
#         OfficeHolidayResponse,
#         OperatoryCreate,
#         OperatoryUpdate,
#         OperatoryResponse,
#         OfficeCreateAllRequest

#     )

# from app.models.office import Office
# from app.models.office_role import OfficeRole

# from app.api.v1.offices.service import (
#     get_office_statement,
#     upsert_office_statement,
#     get_schedule,
#     replace_schedule,
#     OfficeIntegrationCreate,
#     # OfficeIntegrationResponse,
#     list_integrations,
#     create_integration,
#     list_holidays,
#     create_holiday,
#     delete_holiday,
#     list_operatories,
#     create_operatory,
#     update_operatory,
#     delete_operatory,
#     create_office,
#     update_office,
#     delete_office,
#     create_office_all
# )

# from app.api.v1.auth.dependencies import require_office_permission
# from app.api.v1.auth.dependencies import get_current_user

# from app.api.v1.auth.dependencies import get_current_tenant_id

# router = APIRouter(
#     prefix="/offices",
#     tags=["Offices Setup"]
# )





# @router.post(
#     "/all",
#     response_model=OfficeResponse,
#     status_code=status.HTTP_201_CREATED
# )
# def create_office(
#     payload: OfficeCreateAllRequest,
#     db: Session = Depends(get_db),
#     user=Depends(get_current_user),
# ):
#     return create_office_all(
#         db,
#         tenant_id=user.tenant_id,
#         office_payload=payload.office,
#         holidays=payload.holidays,
#         operatories=payload.operatories,
#         integrations=payload.integrations,
#         schedule=payload.schedule,
#         statement=payload.statement,
#     )





# @router.post(
#     "",
#     response_model=OfficeResponse,
#     status_code=status.HTTP_201_CREATED
# )
# def create_new_office(
#     payload: OfficeCreate,
#     db: Session = Depends(get_db),
#     tenant_id: int = Depends(get_current_tenant_id),
#     user=Depends(get_current_user),
# ):
#     return create_office(
#         db,
#         tenant_id=tenant_id,
#         data=payload
#     )


# @router.get("", response_model=List[OfficeResponse])
# def list_offices(
#     db: Session = Depends(get_db),
#     tenant_id: int = Depends(get_current_tenant_id),
# ):
#     return (
#         db.query(Office)
#         .filter(
#             Office.tenant_id == tenant_id,
#             Office.is_active == True
#         )
#         .order_by(Office.office_name)
#         .all()
#     )


# @router.get("/{office_id}", response_model=OfficeResponse)
# def get_office(
#     office_id: int,
#     db: Session = Depends(get_db),
#     tenant_id: int = Depends(get_current_tenant_id),
# ):
#     office = (
#         db.query(Office)
#         .filter(
#             Office.id == office_id,
#             Office.tenant_id == tenant_id
#         )
#         .first()
#     )

#     if not office:
#         raise HTTPException(status_code=404, detail="Office not found")

#     return office



# @router.put("/{office_id}", response_model=OfficeResponse)
# def edit_office(
#     office_id: int,
#     payload: OfficeUpdate,
#     db: Session = Depends(get_db),
#     tenant_id: int = Depends(get_current_tenant_id),
# ):
#     office = (
#         db.query(Office)
#         .filter(
#             Office.id == office_id,
#             Office.tenant_id == tenant_id
#         )
#         .first()
#     )

#     if not office:
#         raise HTTPException(status_code=404, detail="Office not found")

#     return update_office(
#         db,
#         office=office,
#         data=payload
#     )





# @router.get(
#     "/{office_id}/statement",
#     response_model=OfficeStatementResponse#,
#     # dependencies=[Depends(require_office_permission("OFFICE_STATEMENT_VIEW"))]
# )
# def read_statement(office_id: int, db: Session = Depends(get_db)):
#     return get_office_statement(db, office_id)


# @router.put(
#     "/{office_id}/statement",
#     response_model=OfficeStatementResponse,
#     # dependencies=[Depends(require_office_permission("OFFICE_STATEMENT_EDIT"))]
# )
# def update_statement(
#     office_id: int,
#     payload: OfficeStatementUpdate,
#     db: Session = Depends(get_db),
# ):
#     return upsert_office_statement(db, office_id, payload)



# @router.get(
#     "/{office_id}/integrations",
#     response_model=List[OfficeIntegrationResponse],
#     dependencies=[Depends(require_office_permission("OFFICE_INTEGRATION_VIEW"))]
# )
# def get_integrations(office_id: int, db: Session = Depends(get_db)):
#     return list_integrations(db, office_id)


# @router.post(
#     "/{office_id}/integrations",
#     response_model=OfficeIntegrationResponse,
#     dependencies=[Depends(require_office_permission("OFFICE_INTEGRATION_EDIT"))]
# )
# def add_integration(
#     office_id: int,
#     payload: OfficeIntegrationCreate,
#     db: Session = Depends(get_db),
# ):
#     return create_integration(db, office_id, payload)


# @router.get(
#     "/{office_id}/schedule",
#     dependencies=[Depends(require_office_permission("OFFICE_SCHEDULE_VIEW"))]
# )
# def read_schedule(office_id: int, db: Session = Depends(get_db)):
#     return get_schedule(db, office_id)


# @router.put(
#     "/{office_id}/schedule",
#     dependencies=[Depends(require_office_permission("OFFICE_SCHEDULE_EDIT"))]
# )
# def update_schedule(
#     office_id: int,
#     payload: OfficeScheduleUpdate,
#     db: Session = Depends(get_db),
# ):
#     replace_schedule(db, office_id, payload)
#     return {"status": "updated"}



# @router.get(
#     "/{office_id}/operatories",
#     response_model=List[OperatoryResponse],
#     dependencies=[Depends(require_office_permission("OPERATORIES_VIEW"))]
# )
# def get_operatories(office_id: int, db: Session = Depends(get_db)):
#     return list_operatories(db, office_id)


# @router.post(
#     "/{office_id}/operatories",
#     response_model=OperatoryResponse,
#     dependencies=[Depends(require_office_permission("OPERATORIES_MANAGE"))]
# )
# def add_operatory(
#     office_id: int,
#     payload: OperatoryCreate,
#     db: Session = Depends(get_db),
# ):
#     return create_operatory(db, office_id, payload)


# @router.put(
#     "/{office_id}/operatories/{operatory_id}",
#     response_model=OperatoryResponse,
#     dependencies=[Depends(require_office_permission("OPERATORIES_MANAGE"))]
# )
# def edit_operatory(
#     office_id: int,
#     operatory_id: int,
#     payload: OperatoryUpdate,
#     db: Session = Depends(get_db),
# ):
#     return update_operatory(db, operatory_id, payload)


# @router.delete(
#     "/{office_id}/operatories/{operatory_id}",
#     dependencies=[Depends(require_office_permission("OPERATORIES_MANAGE"))]
# )
# def remove_operatory(
#     office_id: int,
#     operatory_id: int,
#     db: Session = Depends(get_db),
# ):
#     delete_operatory(db, operatory_id)
#     return {"status": "deleted"}


# @router.get(
#     "/{office_id}/holidays",
#     response_model=List[OfficeHolidayResponse],
#     dependencies=[Depends(require_office_permission("OFFICE_HOLIDAY_VIEW"))]
# )
# def get_holidays(office_id: int, db: Session = Depends(get_db)):
#     return list_holidays(db, office_id)


# @router.post(
#     "/{office_id}/holidays",
#     response_model=OfficeHolidayResponse,
#     dependencies=[Depends(require_office_permission("OFFICE_HOLIDAY_MANAGE"))]
# )
# def add_holiday(
#     office_id: int,
#     payload: OfficeHolidayCreate,
#     db: Session = Depends(get_db),
# ):
#     return create_holiday(db, office_id, payload)


# @router.delete(
#     "/{office_id}/holidays/{holiday_id}",
#     dependencies=[Depends(require_office_permission("OFFICE_HOLIDAY_MANAGE"))]
# )
# def remove_holiday(
#     office_id: int,
#     holiday_id: int,
#     db: Session = Depends(get_db),
# ):
#     delete_holiday(db, holiday_id)
#     return {"status": "deleted"}


# @router.delete("/{office_id}", status_code=status.HTTP_204_NO_CONTENT)
# def remove_office(
#     office_id: int,
#     db: Session = Depends(get_db),
#     tenant_id: int = Depends(get_current_tenant_id),
# ):
#     office = (
#         db.query(Office)
#         .filter(
#             Office.id == office_id,
#             Office.tenant_id == tenant_id
#         )
#         .first()
#     )

#     if not office:
#         raise HTTPException(status_code=404, detail="Office not found")

#     delete_office(db, office=office)







# @router.get("/next-id")
# def office_setup_2():
#     out = {
#             "nextOfficeId": 1005
#             }


#     return out


# # @router.get("/next-id")
# # def office_setup_3():
# #     out = {
# #             "nextOfficeId": 1005
# #             }
# #     return out

# @router.get("/metadata")
# def office_setup_4():
#     out = {
#             "time_zones": [
#                 "America/New_York",
#                 "America/Chicago",
#                 "America/Denver",
#                 "America/Phoenix",
#                 "America/Los_Angeles"
#             ],
#             "billing_providers": [
#                 {
#                 "id": "prov-001",
#                 "name": "Dr. Sarah Johnson",
#                 "npi": "1234567890",
#                 "license": "LIC-12345"
#                 }
#             ],
#             "fee_schedules": [
#                 {
#                 "id": "fs-001",
#                 "name": "Standard Fee Schedule",
#                 "type": "STANDARD"
#                 },
#                 {
#                 "id": "fs-002",
#                 "name": "UCR California 2024",
#                 "type": "UCR"
#                 }
#             ]
#             }

#     return out


# @router.get("/billing-providers")
# def office_setup_5():
#     out = {
#             "name": "Dr. John Smith",
#             "npi": "1234567890",
#             "license": "LIC-99999"
#             }


#     return out


# @router.post("/billing-providers")
# def office_setup_6():
#     payload = {
#                 "name": "Dr. John Smith",
#                 "npi": "1234567890",
#                 "license": "LIC-99999"
#                 }

#     out = {
#             "id": "prov-009",
#             "name": "Dr. John Smith"
#             }



#     return out



# @router.post("/fee-schedules")
# def office_setup_7():
#     payload = {
#                 "name": "New PPO Schedule",
#                 "type": "STANDARD"
#                 }


#     out = {
#             "name": "New PPO Schedule",
#             "type": "STANDARD"
#             }



#     return out

# # PUT /api/v1/offices/{office_id}/statement


# @router.put("/{office_id}/statement")
# def office_setup_8():
#     payload = {
#                 "messages": {
#                     "general": "...",
#                     "current": "...",
#                     "day30": "...",
#                     "day60": "...",
#                     "day90": "...",
#                     "day120": "..."
#                 },
#                 "settings": {
#                     "correspondence_name": "...",
#                     "statement_name": "...",
#                     "statement_address": "...",
#                     "statement_phone": "...",
#                     "logo_url": None
#                 }
#                 }



#     out = {
#             "messages": {
#                 "general": "...",
#                 "current": "...",
#                 "day30": "...",
#                 "day60": "...",
#                 "day90": "...",
#                 "day120": "..."
#             },
#             "settings": {
#                 "correspondence_name": "...",
#                 "statement_name": "...",
#                 "statement_address": "...",
#                 "statement_phone": "...",
#                 "logo_url": None
#             }
#             }




#     return out



# # GET /api/v1/offices/{office_id}/integration


# @router.get("/{office_id}/integration")
# def office_setup_9():
#     payload = {
#                 "e_claims": {
#                     "vendor_type": "DentalXChange",
#                     "username": "office_user",
#                     "password": "encrypted_or_tokenized"
#                 },
#                 "transworld": {
#                     "accelerator_account": "ACC123",
#                     "collections_account": "COL456",
#                     "user_id": "tw_user",
#                     "password": "encrypted",
#                     "aging_days": 90
#                 },
#                 "imaging_systems": [
#                     {
#                     "index": 1,
#                     "name": "Dexis",
#                     "link_type": "Patient ID",
#                     "mode": "Default"
#                     },
#                     {
#                     "index": 2,
#                     "name": "Carestream",
#                     "link_type": "Chart Number",
#                     "mode": "Custom"
#                     }
#                 ],
#                 "text_messaging": {
#                     "phone_number": "+15551234567",
#                     "verified": True
#                 },
#                 "patient_urls": {
#                     "forms_url": "https://forms.example.com",
#                     "scheduling_url": "https://schedule.example.com",
#                     "financing_url": "https://carecredit.com",
#                     "custom_url_1": "",
#                     "custom_url_2": ""
#                 },
#                 "accepted_cards": ["Visa", "Mastercard"]
#                 }




#     out = payload




#     return out


# # PUT /api/v1/offices/{office_id}/integration


# @router.put("/{office_id}/integration")
# def office_setup_10():
#     payload = {
#                 "e_claims": {
#                     "vendor_type": "DentalXChange",
#                     "username": "office_user",
#                     "password": "encrypted_or_tokenized"
#                 },
#                 "transworld": {
#                     "accelerator_account": "ACC123",
#                     "collections_account": "COL456",
#                     "user_id": "tw_user",
#                     "password": "encrypted",
#                     "aging_days": 90
#                 },
#                 "imaging_systems": [
#                     {
#                     "index": 1,
#                     "name": "Dexis",
#                     "link_type": "Patient ID",
#                     "mode": "Default"
#                     },
#                     {
#                     "index": 2,
#                     "name": "Carestream",
#                     "link_type": "Chart Number",
#                     "mode": "Custom"
#                     }
#                 ],
#                 "text_messaging": {
#                     "phone_number": "+15551234567",
#                     "verified": True
#                 },
#                 "patient_urls": {
#                     "forms_url": "https://forms.example.com",
#                     "scheduling_url": "https://schedule.example.com",
#                     "financing_url": "https://carecredit.com",
#                     "custom_url_1": "",
#                     "custom_url_2": ""
#                 },
#                 "accepted_cards": ["Visa", "Mastercard"]
#                 }




#     out = { "password_set": True }


#     return out



# @router.get("/{office_id}/operatories")
# def office_setup_11():
#     payload = {
#                 "operatories": [
#                     { "id": "op_1", "name": "OP 1", "order": 1, "is_active": True },
#                     { "id": "op_2", "name": "Hygiene 1", "order": 2, "is_active": False }
#                 ]
#                 }





#     out = payload


#     return out




# @router.put("/{office_id}/schedule")
# def office_setup_12():
#     payload = {
#                 "timezone": "America/Los_Angeles",
#                 "week": {
#                     "monday": { "start": "08:00", "end": "17:00", "lunch_start": "12:00", "lunch_end": "13:00", "closed": False },
#                     "tuesday": { "...": "..." }
#                 }
#                 }

#     out = payload


#     return out

# # PUT /api/v1/offices/{office_id}/holidays


# @router.put("/{office_id}/holidays")
# def office_setup_13():
#     payload = {
#                 "holidays": [
#                     {
#                     "id": "hol_1",
#                     "name": "New Year's Day",
#                     "start_date": "2026-01-01",
#                     "end_date": "2026-01-01",
#                     "is_active": True
#                     }
#                 ]
#                 }


#     out = payload


#     return out


# @router.post("/{office_id}/holidays/copy")
# def office_setup_13():
#     payload = {
#                 "from_office_id": 1002,
#                 "mode": "append or overwrite"
#                 }



#     out = payload


#     return out


# @router.post("/{office_id}/holidays/copy")
# def office_setup_14():
#     payload = {
#                 "from_office_id": 1002,
#                 "mode": "append or overwrite"
#                 }



#     out = payload


#     return out

# # GET /api/v1/offices/{office_id}/setup

# @router.post("/{office_id}/holidays/copy")
# def office_setup_15():
#     payload = {
#                 "from_office_id": 1002,
#                 "mode": "append or overwrite"
#                 }



#     out = payload


#     return out


# # PUT /api/v1/offices/{office_id}/advanced
# #
# @router.put("/{office_id}/advanced")
# def office_setup_16():
#     payload = {
#                 "financial": {"..."},
#                 "scheduler": {"..."},
#                 "insurance": {"..."},
#                 "defaults": {"..."},
#                 "patient_checkin": {"..."},
#                 "automation": {"..."}
#                 }



#     out = payload


#     return out

# # PUT /api/v1/offices/{office_id}/smart-assist

# @router.put("/{office_id}/smart-assist")
# def office_setup_17():
#     payload = {
#                 "enabled": True,
#                 "items": { ". . ." }
#                 }

#     out = payload



# # add office api payload

# # {"officeId":1005,"officeName":"Shravan","shortId":"SHRVS","openingDate":"2026-01-14",
# # "address1":"asdddasd","address2":"asdasd","city":"adasdas","state":"ID","zip":"748511",
# # "phone1":"656544","phone1Ext":"212","phone2":"654564","email":"561564",
# # "billingProviderId":"prov-001","billingProviderName":"Dr. Sarah Johnson",
# # "taxId":"4654654654","officeGroup":"adasd","defaultUCRFeeSchedule":"fs-001",
# # "defaultFeeSchedule":"fs-002","schedulerTimeInterval":30,
# # "statementMessages":{"general":"dsfsf","current":"sfdfss","day30":"sfdsfvbx",
# #                     "day60":"fsddsfs","day90":"vcxvxc","day120":"bbbbbbfddd"},
# # "statementSettings":{"correspondenceName":"fgfgffgdds","statementName":"dfgdfgd",
# #                     "statementAddress":"dgfdf","statementPhone":"5555555555555555555"},
# # "eClaims":{"vendorType":"DentalXChange","username":"fdfd","password":"dfgdg"},
# # "transworld":{"acceleratorAccount":"56565","collectionsAccount":"55555555555","userId":"5555",
# #                 "password":"222222222222222222","agingDays":20},
# # "imaging":{"system1":{"name":"Dentiray","linkType":"Patient ID","mode":"Default"},
# # "system2":{"name":"XVWeb","linkType":"Chart Number","mode":"Default"},
# # "system3":{"name":"Apteryx","linkType":"Account Number","mode":"Default"}},
# # "textMessaging":{"phoneNumber":"4544645","verified":true},
# # "patientUrls":{"formsUrl":"dfsssf","schedulingUrl":"xcxcxzv","financingUrl":"zxcfdfd",
# #                 "customUrl1":"zxccz","customUrl2":"zcxxvcvc"},
# # "acceptedCards":["Visa","Mastercard"],
# # "operatories":[{"id":"temp-1767735897671","name":"cxxcv","order":1,"is_active":true},
# #                 {"id":"temp-1767735900239","name":"zxczxcz","order":2,"is_active":true}],
# # "schedule":{"monday":{"closed":false,"start":"07:15","end":"03:21","lunchStart":"03:21",
# #             "lunchEnd":"07:15"},"thursday":{"closed":true},"wednesday":{"closed":true}},
# # "holidays":[{"id":"temp-1767735933280","name":"zxcxzcxz","fromDate":"2026-01-20",
# #             "toDate":"2026-01-23","is_active":true}],
# # "advanced":{"annualFinanceChargePercent":54,
# #             "minimumBalance":456,"minimumFinanceCharge":45,"daysBeforeFinanceCharge":456,
# #             "salesTaxPercent":45.8,"insuranceGroup":"sdasdas","schedulerEndDate":"2026-01-09",
# #             "eligibilityThresholdDays":23,"defaultAppointmentDuration":32,"defaultAreaCode":"232",
# #             "defaultCity":"xzxz","defaultState":"zx","defaultZip":"12123",
# #             "preferredProvider":"Dr. Sarah Johnson","isOrthoOffice":true,"hipaaNotice":true,
# #             "consentForm":true,"additionalConsentForm":true,
# #             "automatedCampaignsEffectiveDate":"2026-01-30"},
# # "smartAssist":{"enabled":true,"items":{"payment":{"enabled":true,"includeBal":true},
# # "eligibility":{"enabled":true,"frequency":"Every Year"},
# # "ledgerPosting":{"enabled":true,"frequency":"Every Year"}}}}

# # from app.models.role import Role
# # from app.models.user_role import UserRole

# # print(Role.__mapper__.relationships.keys())
# # print(UserRole.__mapper__.relationships.keys())
