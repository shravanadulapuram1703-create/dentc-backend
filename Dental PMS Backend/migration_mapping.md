# Dental PMS — Data Migration Mapping Guide

**Source System:** Denticon (dental PMS)  
**Practice Group:** Excel Dental (PGID = 2829)  
**Source Format:** Tab-delimited `.txt` files, header on row 1, data from row 2  
**Target System:** Custom Dental PMS (simplified schema)

---

## Source Files Overview

| Source File | What It Contains | Target Table(s) |
|---|---|---|
| `PGroup.txt` | Practice group / tenant | `tenants` |
| `Office.txt` | Office locations + settings | `offices` |
| `Providers.txt` | Dentists, hygienists, staff | `providers` |
| `Operatory.txt` | Treatment rooms | `operatories` |
| `RespParty.txt` | Patients + guarantors (demographics) | `patients` |
| `PatInsPlans.txt` | Patient ↔ insurance plan link | `patient_insurance` |
| `InsPlans.txt` | Insurance plan details | `insurance_plans` |
| `Carrier.txt` | Insurance companies | `insurance_carriers` |
| `Codes.txt` | ADA + custom procedure codes | `procedure_codes` |
| `FeeScheD.txt` | Fee amounts per code | `procedure_codes.default_fee` |
| `AppointmentHeader.txt` | Appointment header records | `appointments` |
| `AppointmentDetails.txt` | Procedures attached to appointments | `appointment_procedures` |
| `LEDGER/*.txt` (25 files) | All financial transactions | `patient_procedures` (LTYPE=C), `patient_payments` (LTYPE=P/I/A) |
| `CLAIMH/*.txt` (2 files) | Insurance claims | `insurance_claims` |
| `ChartActivity.txt` | Tooth conditions/findings | `chart_conditions` |
| `ProgressNotes_Archive.txt` | Clinical progress notes | `progress_notes` |
| `PatFlashAlerts.txt` | Patient alert messages | `patient_alerts` |
| `PatRx.txt` | Prescriptions | `prescriptions` |
| `TCLOCK.txt` | Staff time clock entries | *(Phase 2)* |
| `ChartPerioActivity.txt` | Perio exam data | *(Phase 2)* |
| `PatMedicalHistoryH.txt` | Medical history header | *(Phase 2)* |

---

## Migration Run Order

Run in this exact order to satisfy foreign key dependencies:

```
Step 1:  tenants            ← PGroup.txt
Step 2:  offices            ← Office.txt
Step 3:  providers          ← Providers.txt
Step 4:  operatories        ← Operatory.txt
Step 5:  insurance_carriers ← Carrier.txt
Step 6:  insurance_plans    ← InsPlans.txt
Step 7:  procedure_codes    ← Codes.txt  (+fees from FeeScheD.txt)
Step 8:  patients           ← RespParty.txt
Step 9:  patient_insurance  ← PatInsPlans.txt
Step 10: patient_alerts     ← PatFlashAlerts.txt
Step 11: appointments       ← AppointmentHeader.txt
Step 12: appointment_procedures ← AppointmentDetails.txt
Step 13: treatment_plans    ← AppointmentDetails.txt (TREATPLANID != 0)
Step 14: patient_procedures ← LEDGER/*.txt (LTYPE = 'C')
Step 15: patient_payments   ← LEDGER/*.txt (LTYPE = 'P' or 'I')
Step 16: insurance_claims   ← CLAIMH/*.txt
Step 17: chart_conditions   ← ChartActivity.txt
Step 18: progress_notes     ← ProgressNotes_Archive.txt
Step 19: prescriptions      ← PatRx.txt
```

---

## Entity-by-Entity Field Mapping

### 1. Tenants ← `PGroup.txt`

| Source Field | Source Value | Target Field | Notes |
|---|---|---|---|
| `PGID` | `2829` | `legacy_id` | Store original |
| `PGNAME` | `Excel Dental of Moon Township` | `name` | |
| *(derived)* | `CLINIC-2829` | `code` | Generate from PGID |
| *(hardcoded)* | `true` | `is_active` | |

---

### 2. Offices ← `Office.txt`

| Source Field | Target Field | Transform |
|---|---|---|
| `OID` | `legacy_id` | Store as-is |
| `OID` | `office_code` | Prefix: `"O-" + OID` |
| `OFFICENAME` | `name` | As-is |
| `ADDRESS` | `address_line1` | |
| `ADDRESS2` | `address_line2` | |
| `CITY` | `city` | |
| `STATE` | `state` | |
| `ZIP` | `zip` | |
| `PHONE1` | `phone` | |
| `FAX` | `fax` | |
| `EMAIL` | `email` | |
| `APPINTERVAL` | `slot_interval_minutes` | Default 10 if blank |
| `MONSTART` / `MONEND` | `schedule_start_hour` / `schedule_end_hour` | Parse time, extract hour |
| `PGID` | `tenant_id` | Lookup `tenants.id` WHERE `legacy_id = PGID` |

---

### 3. Providers ← `Providers.txt`

| Source Field | Target Field | Transform |
|---|---|---|
| `PROVIDERID` | `legacy_id` | |
| `PROVIDERID` | `id` | Use as-is or generate new ID |
| `FNAME + " " + LNAME` | `name` | Concatenate |
| `TITLE` | `title` | |
| `PROVIDERTYPE` | `role` | `1` → `'dentist'`, `2` → `'hygienist'`, `3` → `'staff'` |
| `NPIID` | `npi` | |
| `LICENSENUM` | `license` | |
| `TAXID` | `tax_id` | |
| `SHORTID` | `short_id` | |
| `ACTIVE` | `is_active` | `'Y'` → `true`, `'N'` → `false` |
| `OID` | `office_id` | Lookup `offices.id` WHERE `legacy_id = OID` |
| `PGID` | *(via offices.tenant_id)* | |

---

### 4. Operatories ← `Operatory.txt`

| Source Field | Target Field | Transform |
|---|---|---|
| `OPERATORYID` | `legacy_id` | |
| `OPERATORYID` | `id` | Use as-is |
| `DESCR` | `name` | |
| `OID` | `office_id` | Lookup `offices.id` |

---

### 5. Insurance Carriers ← `Carrier.txt`

| Source Field | Target Field | Transform |
|---|---|---|
| `CARRIERID` | `legacy_id` | |
| `NAME` | `name` | |
| `PAYERID` | `payer_id` | Electronic payer ID |
| `PHONE` | `phone` | |
| `ADDRESS` | `address` | |
| `CITY`, `STATE`, `ZIP` | `city`, `state`, `zip` | |
| `PGID` | `tenant_id` | Lookup |

---

### 6. Insurance Plans ← `InsPlans.txt`

| Source Field | Target Field | Transform |
|---|---|---|
| `INSPLANID` | `legacy_id` | |
| `CARRIERID` | `carrier_id` | Lookup `insurance_carriers.id` WHERE `legacy_id = CARRIERID` |
| `GROUPNUMBER` | `group_number` | |
| `PLANTYPE` | `plan_type` | `1`=PPO, `2`=HMO, `3`=Medicaid, `4`=Indemnity, `5`=Cap |
| `INDIVIDUALMAX` | `individual_max` | |
| `INDIVIDUALDEDUCTIBLE` | `individual_deductible` | |
| `INDIVIDUALORTHOMAX` | `ortho_max` | |
| `FAMILYMAX` | `family_max` | |
| `ANNIVDATE` | `anniversary_date` | Parse date |

---

### 7. Procedure Codes ← `Codes.txt` + `FeeScheD.txt`

| Source Field | Target Field | Transform |
|---|---|---|
| `CODE` | `code` | As-is (e.g. `D0150`) |
| `DESCR` | `description` | |
| `INSCATEGORYID` | `category` | Map integer to text (see below) |
| `PROCTIME` | `default_duration_minutes` | |
| `TOOTHNUMREQ` | `requires_tooth` | `1` → `true` |
| `TOOTHSURFREQ` | `requires_surface` | `1` → `true` |
| `QUADRANTREQ` | `requires_quadrant` | `1` → `true` |
| `ISACTIVE` | `is_active` | `'Y'` → `true` |

**For default_fee:** Join `FeeScheD.txt` ON `CODE = CODE` and use the `PATAMT` from the standard fee schedule (FEEID = office default fee schedule).

**Category mapping (INSCATEGORYID):**
```
1  → Diagnostic
2  → Preventive
3  → Restorative
4  → Endodontics
5  → Periodontics
6  → Prosthodontics (Removable)
7  → Maxillofacial Prosthetics
8  → Implant Services
9  → Prosthodontics (Fixed)
10 → Oral & Maxillofacial Surgery
11 → Orthodontics
12 → Adjunctive General Services
0  → Other
```

---

### 8. Patients ← `RespParty.txt`

**Key note:** In Denticon, `RespParty.txt` stores both patients AND their guarantors.  
- Each unique `RPID` = one person (patient or responsible party).
- When a patient is their own guarantor, RPID == PATID in other tables.
- Migrate **every unique RPID** as a `patients` row. Relationships (child→parent, spouse) can be handled in Phase 2.

| Source Field | Target Field | Transform |
|---|---|---|
| `RPID` | `legacy_id` | |
| `OID` | `home_office_id` | Lookup `offices.id` |
| `FNAME` | `first_name` | |
| `LNAME` | `last_name` | |
| `NICKNAME` | `preferred_name` | |
| `TITLE` | `title` | |
| `BIRTHDATE` | `dob` | Parse datetime, take date only |
| `SEX` | `gender` | `'M'` → `'Male'`, `'F'` → `'Female'`, `''` → `NULL` |
| `SSN` | `ssn` | ⚠️ Encrypt in app layer before storing |
| `HOMEPHONE` | `phone` | |
| `WORKPHONE` | `work_phone` | |
| `CELLPHONE` | `cell_phone` | |
| `EMAIL` | `email` | Lowercase, trim |
| `ADDRESS` | `address_line1` | |
| `ADDRESS2` | `address_line2` | |
| `CITY` | `city` | |
| `STATE` | `state` | |
| `ZIP` | `zip` | |
| `MSTATUS` | `marital_status` | `'S'`=Single, `'M'`=Married, `'D'`=Divorced, `'W'`=Widowed |
| `NOEMAILSTMT` | `no_auto_email` | `'True'` → `true` |
| `ISSENDSTMT` | `no_statements` | Invert: `'False'` → `true` (no statements) |
| `PGID` | `tenant_id` | Lookup |

**Chart number:** Denticon doesn't export a chart number in `RespParty.txt`. Generate as `"CH-" + RPID` during migration.

---

### 9. Patient Insurance ← `PatInsPlans.txt`

| Source Field | Target Field | Transform |
|---|---|---|
| `PATID` | `patient_id` | Lookup `patients.id` WHERE `legacy_id = PATID` |
| `INSPLANID` | `insurance_plan_id` | Lookup `insurance_plans.id` WHERE `legacy_id = INSPLANID` |
| `INSTYPE` | `insurance_type` | `'P'` → `'primary'`, `'S'` → `'secondary'` |
| `RPID` | `subscriber_patient_id` | Lookup `patients.id` WHERE `legacy_id = RPID` |
| `RELTOPAT` | `relationship` | `'P'`=self, `'S'`=spouse, `'C'`=child, `'O'`=other |
| `INDDEDREM` | `deductible_remaining` | |
| `INDMAXREM` | `max_remaining` | |
| `INDORTHOREM` | `ortho_remaining` | |

---

### 10. Patient Alerts ← `PatFlashAlerts.txt`

| Source Field | Target Field | Transform |
|---|---|---|
| `FLASHALERTID` | `legacy_id` | |
| `PATID` | `patient_id` | Lookup `patients.id` WHERE `legacy_id = PATID` |
| `MESSAGE` | `alert` | |
| `ISBLOCKCHARGES` | `blocks_charges` | `'True'` → `true` |
| `ISACTIVE` | `is_active` | `'True'` → `true` |

---

### 11. Appointments ← `AppointmentHeader.txt`

| Source Field | Target Field | Transform |
|---|---|---|
| `APPTID` | `legacy_id` | |
| `PATID` | `patient_id` | Lookup `patients.id` WHERE `legacy_id = PATID` |
| `PROVIDERID` | `provider_id` | Lookup `providers.id` WHERE `legacy_id = PROVIDERID` |
| `OPERATORYID` | `operatory_id` | Lookup `operatories.id` WHERE `legacy_id = OPERATORYID` |
| `OID` | `office_id` | Lookup `offices.id` WHERE `legacy_id = OID` |
| `APPTDATE` | `date` + `start_time` | Split datetime: date part → `date`, time part → `start_time` |
| `APPTLENGTH` | `duration` | Integer minutes |
| `APPTDATE` + `APPTLENGTH` | `end_time` | `start_time + duration` |
| `APPTSTATUS` | `status` | See status mapping below |
| `ISMISSED` | `is_missed` | `'True'` → `true` |
| `ISCANCELLED` | `is_cancelled` | `'True'` → `true` |
| `PRODTYPE` | `procedure_label` | |
| `APPTNOTES` | `notes` | |
| `ISLAB` | `has_lab` | `'True'` → `true` |
| `LABCOST` | `lab_cost` | |
| `LABSENTON` | `lab_sent_on` | Parse date |
| `LABDUEON` | `lab_due_on` | Parse date |
| `LABRECVDON` | `lab_received_on` | Parse date |

**Appointment Status Mapping:**

| Denticon `APPTSTATUS` | Target `status` |
|---|---|
| `1` | `Scheduled` |
| `2` | `Unconfirmed` |
| `3` | `Confirmed` |
| `4` | `Left Message` |
| `5` | `In Reception` |
| `6` | `Available` |
| `7` | `In Operatory` |
| `8` | `Checked Out` |
| `9` | `Missed` (also check ISMISSED) |
| `X` or when `ISPOSTED='True'` | `Checked Out` |
| When `ISCANCELLED='True'` | `Cancelled` |
| When `ISMISSED='True'` | `Missed` |

**Skip:** Rows where `PATID = 0` — these are blocked/closed times on the calendar, not real appointments.

---

### 12. Appointment Procedures ← `AppointmentDetails.txt`

| Source Field | Target Field | Transform |
|---|---|---|
| `APPTID` | `appointment_id` | Lookup `appointments.id` WHERE `legacy_id = APPTID` |
| `ADACODE` (or `CODE`) | `procedure_code` | Use `ADACODE` first; fall back to `CODE` |
| `PROVIDERID` | `provider_id` | Lookup |
| `TH` | `tooth` | |
| `SURF` | `surface` | |
| `DESCR` | `description` | |
| `FEE` | `fee` | |
| `ESTINS` | `insurance_estimate` | |
| `STATUS` | `status` | `'C'` → `'Completed'`, `''` → `'Planned'` |

---

### 13. Patient Procedures ← `LEDGER/*.txt` (rows where `LTYPE = 'C'`)

Denticon uses the Ledger as the master record for all completed procedures.  
Filter: `LTYPE = 'C'` (charge) and `ISVOID != 'True'`

| Source Field | Target Field | Transform |
|---|---|---|
| `LEDGERID` | `legacy_id` | |
| `PATID` | `patient_id` | Lookup |
| `APPTDID` | `appointment_id` | Lookup `appointments.id` WHERE `legacy_id = APPTDID` (if non-zero) |
| `ADACODE` (or `CODE`) | `procedure_code` | Use ADACODE first |
| `DOSDATE` | `date_of_service` | Parse date; fallback to `TRANDATE` |
| `PROVIDERID` | `provider_id` | Lookup |
| `OID` | `office_id` | Lookup |
| `TH` | `tooth` | |
| `SURF` | `surface` | |
| `AMOUNT` | `fee` | |
| `ESTINS` | `insurance_estimate` | |
| `APPLYTO` | `apply_to` | `'P'` or `'I'` |
| `BILLINGORDER` | `billing_order` | `'D   '` → `'primary'`, `'S   '` → `'secondary'` (trim whitespace) |
| `CLAIMID` | `claim_id` | Lookup `insurance_claims.id` WHERE `legacy_id = CLAIMID` |
| `NOTES` | `notes` | |

---

### 14. Patient Payments ← `LEDGER/*.txt` (rows where `LTYPE = 'P'` or `'I'`)

Filter: `LTYPE IN ('P', 'I', 'A')` — payments and adjustments

| Source Field | Target Field | Transform |
|---|---|---|
| `LEDGERID` | `legacy_id` | |
| `PATID` | `patient_id` | Lookup |
| `TRANDATE` | `payment_date` | Parse date |
| `AMOUNT` | `amount` | Store as absolute value (source may be negative) |
| `LTYPE` | `payment_type` | `'P'`→`'patient'`, `'I'`→`'insurance'`, `'A'`→`'adjustment'` |
| `TYPE2` | `payment_method` | `'CA'`→`'cash'`, `'CK'`→`'check'`, `'CC'`→`'card'`, `'EFT'`→`'ach'` |
| `CHECKNO` | `check_number` | |
| `NOTES` | `notes` | |

---

### 15. Insurance Claims ← `CLAIMH/*.txt`

| Source Field | Target Field | Transform |
|---|---|---|
| `CLAIMID` | `legacy_id` + `claim_number` | |
| `PATID` | `patient_id` | Lookup |
| `CLAIMSTATUS` | `status` | See mapping below |
| `CLAIMTYPE` | `claim_type` | `'P'`→`'primary'`, `'S'`→`'secondary'` |
| `CLAIMDOSDATE` | `date_of_service_from` + `date_of_service_to` | Same date for both if single DOS |
| `CLAIMAMT` | `total_billed` | |
| `RECVDAMT` | `total_paid` | |
| `CLAIMSENTDATE` | `submitted_date` | |
| `CARRIERID` | `carrier_id` | Lookup via RESPPLANID → InsPlans → Carrier |
| `NOTES` | `notes` | |

**Claim Status Mapping:**

| Denticon `CLAIMSTATUS` | Target `status` |
|---|---|
| `S` | `submitted` |
| `P` | `pending` |
| `R` | `paid` |
| `H` | `draft` (on hold) |
| `D` | `denied` |
| `C` | `closed` |

---

### 16. Chart Conditions ← `ChartActivity.txt`

| Source Field | Target Field | Transform |
|---|---|---|
| `CHARTID` | `legacy_id` | |
| `PATID` | `patient_id` | Lookup |
| `OID` | `office_id` | Lookup |
| `ACTDATE` | `activity_date` | Parse date |
| `TH` | `tooth` | |
| `SURF` | `surface` | |
| `REGION` | `region` | |
| `DESCR` | `description` | |
| `CONDITION` | `condition_code` | |
| `CODE` | `procedure_code` | |
| `PROVIDERID` | `provider_id` | Lookup |
| `CHARTAS` | `chart_as` | |
| `INACTIVE` | `is_inactive` | `'True'` → `true` |
| `NOTES` | `notes` | |

---

### 17. Progress Notes ← `ProgressNotes_Archive.txt`

| Source Field | Target Field | Transform |
|---|---|---|
| `PROGNOTESID` | `legacy_id` | |
| `PATID` | `patient_id` | Lookup |
| `OID` | `office_id` | Lookup |
| `DOS` | `note_date` | Parse date |
| `NOTES` | `notes` | Plain text |
| `HTMLNOTES` | `notes_html` | Rich text if present |
| `TH` | `tooth` | |
| `ISDELETED` | `is_deleted` | `'True'` → `true` |

---

### 18. Prescriptions ← `PatRx.txt`

| Source Field | Target Field | Transform |
|---|---|---|
| `PATRXID` | `legacy_id` | |
| `PATID` | `patient_id` | Lookup |
| `RXDATE` | `rx_date` | Parse date |
| `DRUGNAME` | `drug_name` | |
| `DISPENSE` | `dispense` | |
| `SIG` | `sig` | |
| `REFILL` | `refills` | Parse integer |
| `PROVIDERID` | `provider_id` | Lookup |
| `NOTES` | `notes` | |
| `ISACTIVE` | `is_active` | |

---

## Common Data Transformation Rules

### Date Parsing
Denticon dates are in format `MM/DD/YYYY HH:MM:SS`.  
Invalid/placeholder dates to treat as `NULL`: `01/01/1900`, empty string `""`.

```python
def parse_denticon_date(val):
    if not val or '1900' in val:
        return None
    return datetime.strptime(val.strip(), '%m/%d/%Y %H:%M:%S')
```

### Boolean Parsing
Denticon booleans are strings: `'True'` / `'False'`.
```python
def parse_bool(val):
    return val.strip().lower() == 'true'
```

### Phone Normalization
Source phones are 10-digit strings (e.g. `4123757541`). Store as-is; format in the UI layer.

### Legacy ID Lookups
Build in-memory lookup dictionaries during migration to avoid repeated DB queries:
```python
office_map     = { row['OID']: db_office_id }
provider_map   = { row['PROVIDERID']: db_provider_id }
patient_map    = { row['RPID']: db_patient_id }
carrier_map    = { row['CARRIERID']: db_carrier_id }
ins_plan_map   = { row['INSPLANID']: db_plan_id }
appointment_map = { row['APPTID']: db_appointment_id }
claim_map      = { row['CLAIMID']: db_claim_id }
```

### Text Encoding
Source files use Windows-1252 encoding (common for older Windows apps).  
Open files with: `open(path, encoding='cp1252')` in Python.

### File Parsing
All source files are tab-delimited with quoted string values.
```python
import csv
with open(path, 'r', encoding='cp1252') as f:
    reader = csv.reader(f, delimiter='\t', quotechar='"')
    headers = next(reader)  # row 1 = headers
    for row in reader:
        record = dict(zip(headers, row))
```

---

## Known Data Quirks

1. **PATID vs RPID:** In some tables (like `PatInsPlans.txt`), PATID is the patient but RPID is the subscriber/guarantor. They may be the same person or different.

2. **Blocked appointments:** `AppointmentHeader.txt` rows with `PATID = 0` are calendar blocks (holidays, closures), not real appointments. Skip these during migration or store separately.

3. **Ledger has everything:** Denticon's `LEDGER/*.txt` is split across 25+ files (likely by office or date range). Concatenate all files; they all have the same column structure.

4. **CLAIMH has 2 files:** Same split — concatenate `CLAIMH/1.txt` and `CLAIMH/2.txt`.

5. **APPTH_ARCHIVE:** Archived appointment headers — migrate these alongside `AppointmentHeader.txt` if you want full history.

6. **Ledger_archive.txt:** Archived ledger rows — include for complete financial history.

7. **Time format in Office.txt:** Office hours are stored as full datetime strings (`01/01/1900 08:00:00`). Extract only the time portion.

8. **ADACODE vs CODE:** In `AppointmentDetails.txt` and `LEDGER/*.txt`, `ADACODE` is the standard ADA code (e.g. `D0150`), while `CODE` may be a custom code. Always prefer `ADACODE` for matching to `procedure_codes`.

9. **Empty PGID rows:** Last row in some files is empty or just `3\t`. Skip rows where PGID is blank.

---

## UI Display Mapping

When displaying migrated data in the UI, use `legacy_id` to cross-reference the original system if needed. Key display fields per entity:

| UI Screen | Key Display Fields | Source |
|---|---|---|
| Patient chart | first_name, last_name, dob, chart_no, phone, email | `patients` |
| Patient insurance card | carrier name, plan, group_number, subscriber_id | `insurance_carriers`, `insurance_plans`, `patient_insurance` |
| Appointment calendar | date, time, patient name, provider, operatory, status | `appointments` + joins |
| Ledger/charges | date_of_service, procedure_code, description, fee, billing_status | `patient_procedures` + `procedure_codes` |
| Payments | payment_date, amount, payment_type, payment_method | `patient_payments` |
| Claims | claim_number, status, total_billed, total_paid, submitted_date | `insurance_claims` |
| Progress notes | note_date, notes | `progress_notes` |
| Prescriptions | rx_date, drug_name, sig, provider | `prescriptions` |
| Alerts | alert message (show on patient load) | `patient_alerts` |
| Chart conditions | tooth, description, activity_date | `chart_conditions` |
