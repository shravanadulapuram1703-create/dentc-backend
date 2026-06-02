# 📊 Account Setup - Complete Data Definition

**Page:** `/setup/account-info`  
**Purpose:** Manage account configuration, communication settings, holidays, and online registration consent forms  
**Database Design:** Production-ready schema for backend implementation

---

## 📑 TABLE OF CONTENTS

1. [Tab 1: Basic](#tab-1-basic)
2. [Tab 2: Advanced](#tab-2-advanced)
3. [Tab 3: Holidays](#tab-3-holidays)
4. [Tab 4: Communications](#tab-4-communications)
5. [Tab 5: Online Registration](#tab-5-online-registration)
6. [Dropdown Metadata](#dropdown-metadata)
7. [Database Design](#database-design)
8. [API Endpoints](#api-endpoints)

---

## TAB 1: BASIC

### **Field Definitions**

| field_name | label | data_type | is_required | default_value | max_length | example_value | description |
|------------|-------|-----------|-------------|---------------|------------|---------------|-------------|
| `id` | ID | uuid | true | auto-generated | 36 | `acc-001` | Primary key, auto-generated UUID |
| `account_number` | Dental Account # | string | true | auto-generated | 20 | `100123` | Auto-generated, read-only identifier |
| `account_name` | Account Name | string | true | null | 200 | `Smile Bright Dental Group` | Official business name |
| `account_short_id` | Account Short ID | string | true | null | 50 | `smilebright` | Lowercase slug for subdomain/login prefix |
| `contact_first_name` | Contact First Name | string | false | null | 100 | `Sarah` | Primary contact first name |
| `contact_last_name` | Contact Last Name | string | false | null | 100 | `Johnson` | Primary contact last name |
| `corporate_address` | Corporate Address | string | false | null | 500 | `1234 Main Street, Suite 100` | Corporate headquarters street address |
| `corporate_city` | City | string | false | null | 100 | `San Francisco` | Corporate city |
| `corporate_state` | State | enum | false | null | 2 | `CA` | US state abbreviation (see dropdown metadata) |
| `corporate_zip` | ZIP Code | string | false | null | 10 | `94102` | US ZIP code (5 or 9 digits) |
| `statement_address` | Statement Address | string | false | null | 500 | `1234 Main Street, Suite 100` | Billing/statement mailing address |
| `statement_city` | City | string | false | null | 100 | `San Francisco` | Statement city |
| `statement_state` | State | enum | false | null | 2 | `CA` | US state abbreviation |
| `statement_zip` | ZIP Code | string | false | null | 10 | `94102` | Statement ZIP code |
| `email` | Email | string | true | null | 255 | `billing@smilebright.com` | Primary contact email (validated format) |
| `phone` | Phone | string | false | null | 20 | `(415) 555-1234` | Primary phone number |
| `phone_2` | Phone 2 | string | false | null | 20 | `(415) 555-5678` | Secondary phone number |
| `culture_code` | Current Culture | enum | false | `en-US` | 10 | `en-US` | Locale for date/currency format |
| `logo_url` | Corporate Logo | string | false | null | 2000 | `https://...` | URL or base64 data URI for logo |
| `custom_1` | Custom 1 | string | false | null | 500 | `` | User-defined custom field |
| `custom_2` | Custom 2 | string | false | null | 500 | `` | User-defined custom field |

### **Business Rules**

- `account_number` is auto-generated and read-only
- `account_short_id` must be lowercase, alphanumeric + hyphens only
- `email` must pass RFC 5322 email validation
- `logo_url` accepts image/jpeg or image/png, max 2MB
- Logo uploaded as base64 or stored in cloud storage (S3/Azure Blob)

---

## TAB 2: ADVANCED

### **Field Definitions**

#### **Ledger Colors Section**

| field_name | label | data_type | is_required | default_value | example_value | description |
|------------|-------|-----------|-------------|---------------|---------------|-------------|
| `procedure_color` | Procedures | enum | false | `DarkGray` | `DarkGray` | Color name for procedure ledger entries |
| `insurance_payment_color` | Insurance Payments | enum | false | `Teal` | `Teal` | Color name for insurance payment entries |
| `claim_lines_color` | Claim Lines | enum | false | `Purple` | `Purple` | Color name for claim line entries |
| `patient_payment_color` | Patient Payments | enum | false | `Green` | `Green` | Color name for patient payment entries |
| `adjustment_color` | Adjustments | enum | false | `Amber` | `Amber` | Color name for adjustment entries |
| `statement_lines_color` | Statement Lines | enum | false | `Blue` | `Blue` | Color name for statement line entries |
| `notes_lines_color` | Notes Lines | enum | false | `LightGray` | `LightGray` | Color name for ledger note entries |

#### **Options Section**

| field_name | label | data_type | is_required | default_value | example_value | description |
|------------|-------|-----------|-------------|---------------|---------------|-------------|
| `enable_full_screen` | Enable Full Screen | boolean | false | false | true | Allow full-screen mode in scheduler |
| `max_treatment_plan_discount` | Maximum Treatment Plan Discount (%) | decimal(5,2) | false | 0.00 | 15.50 | Max discount % allowed on treatment plans (0-100) |
| `only_show_office_items` | Only Show Office Items in Default Patient Fee Schedule | boolean | false | false | true | Filter procedures by patient's assigned office |
| `statement_close_out_individual` | Statement Close Out Individual Statement | boolean | false | false | true | Close ledger individually per statement |
| `auto_post_periodic_charges` | Auto-post Periodic Contract Charges | boolean | false | false | true | Auto-generate recurring contract charges |
| `show_flash_alerts_insurance` | Show Patient Flash Alerts if Insurance is Not Eligible | boolean | false | false | true | Display eligibility failure alerts |
| `pronoun_field_visible` | Pronoun Field Visible | boolean | false | false | true | Show pronoun field in patient forms |

#### **Default Settings Section**

| field_name | label | data_type | is_required | default_value | example_value | description |
|------------|-------|-----------|-------------|---------------|---------------|-------------|
| `charting_option` | Charting Option | enum | false | `modal` | `modal` | Default charting UI style (modal/submenu/tabbed) |
| `default_charting_tab` | Default Charting Tab | enum | false | `treatment` | `treatment` | Default tab in charting screen |
| `password_expiration_days` | User Password Expiration Limit (days) | integer | false | 90 | 90 | Days before password expires (0 = never) |
| `scheduler_show_non_working_days` | Scheduler – Show Non Working Days | boolean | false | false | true | Display non-working days in scheduler |
| `default_fee_increase_code` | Default Fee Increase Code | string | false | null | `ADJ-INC` | Default adjustment code for fee increases |
| `default_write_off_code` | Default Write Off Code | string | false | null | `ADJ-WO` | Default adjustment code for write-offs |

#### **Required Fields Section**

| field_name | label | data_type | is_required | default_value | example_value | description |
|------------|-------|-----------|-------------|---------------|---------------|-------------|
| `patient_dob_required` | Patient DOB | boolean | false | false | true | Make DOB required in patient records |
| `patient_ssn_required` | Patient SSN | boolean | false | false | false | Make SSN required in patient records |
| `patient_email_required` | Patient Email | boolean | false | false | true | Make email required in patient records |
| `patient_phone_required` | Patient Phone | boolean | false | false | true | Make phone required in patient records |
| `patient_address_required` | Patient Address | boolean | false | false | true | Make address required in patient records |
| `responsible_party_required` | Responsible Party | boolean | false | false | true | Make responsible party required |

#### **Third Party Settings Section**

| field_name | label | data_type | is_required | default_value | example_value | description |
|------------|-------|-----------|-------------|---------------|---------------|-------------|
| `edi_vendor` | EDI Vendor | enum | false | null | `nea` | Electronic data interchange vendor |
| `transworld_enabled` | Transworld (Collection Agency) | boolean | false | false | true | Enable Transworld collections integration |
| `xvweb_enabled` | XVWeb (Imaging) | boolean | false | false | true | Enable XVWeb imaging system |
| `cloud9_enabled` | Cloud 9 (Ortho Software) | boolean | false | false | true | Enable Cloud 9 orthodontics software |

#### **Payment Portal Section**

| field_name | label | data_type | is_required | default_value | example_value | description |
|------------|-------|-----------|-------------|---------------|---------------|-------------|
| `payment_portal_posting_office` | Posting Office | enum | false | null | `main` | Which office receives online payments |
| `post_payment_to_responsible_party` | Post Payment to Responsible Party | boolean | false | false | true | Apply payments to responsible party ledger |

#### **AI Assist Section**

| field_name | label | data_type | is_required | default_value | example_value | description |
|------------|-------|-----------|-------------|---------------|---------------|-------------|
| `ai_assist_org_id` | Organization ID | string | false | null | `org-xxxxxxxxxx` | AI service organization identifier |
| `ai_assist_client_id` | Client ID | string | false | null | `client-xxxxxxxxxx` | AI service client ID |
| `ai_assist_client_secret` | Client Secret | encrypted_string | false | null | `••••••••••` | Encrypted AI service client secret |

---

## TAB 3: HOLIDAYS

### **Field Definitions**

| field_name | label | data_type | is_required | default_value | example_value | description |
|------------|-------|-----------|-------------|---------------|---------------|-------------|
| `id` | ID | uuid | true | auto-generated | `hol-001` | Primary key |
| `account_id` | Account ID | uuid | true | null | `acc-001` | Foreign key to accounts table |
| `holiday_date` | Date | date | true | null | `2026-01-01` | Holiday date (YYYY-MM-DD) |
| `holiday_name` | Name | string | true | null | `New Year's Day` | Holiday name |
| `status` | Status | enum | false | `CLOSED` | `CLOSED` | Office status (CLOSED/OPEN/HALF_DAY) |
| `holiday_type` | Type | enum | false | `Custom` | `Federal` | Holiday type (Federal/Custom) |
| `is_recurring` | Recurring | boolean | false | false | true | Recurs annually if true |

### **Business Rules**

- Bulk delete must check for existing appointments on holiday dates
- `is_recurring` = true means auto-generate for subsequent years
- Federal holidays can be imported via "Add Federal Holidays" wizard
- Date range closures create individual holiday records per day

---

## TAB 4: COMMUNICATIONS

### **Field Definitions**

#### **Business Information Section**

| field_name | label | data_type | is_required | default_value | max_length | example_value | description |
|------------|-------|-----------|-------------|---------------|------------|---------------|-------------|
| `business_name` | Business Name | string | true | null | 200 | `Smile Dental Group` | Legal business name |
| `region_of_operations` | Region of Operations | string | true | null | 100 | `United States` | Operating region |
| `country` | Country | string | true | null | 100 | `United States` | Country of operations |
| `comm_address_line_1` | Address Line 1 | string | true | null | 500 | `123 Main Street, Suite 200` | Business address |
| `comm_city` | City | string | true | null | 100 | `Los Angeles` | Business city |
| `comm_state` | State | enum | true | null | 2 | `CA` | State abbreviation |
| `comm_zip` | ZIP Code | string | true | null | 10 | `90210` | ZIP code |
| `ein` | EIN (Employer Identification Number) | encrypted_string | false | null | 20 | `XX-XXX1234` | Encrypted EIN (masked in UI) |
| `website` | Website | string | true | null | 500 | `https://www.smiledental.com` | Business website URL |

#### **Business Contact Section**

| field_name | label | data_type | is_required | default_value | max_length | example_value | description |
|------------|-------|-----------|-------------|---------------|------------|---------------|-------------|
| `comm_contact_first_name` | Contact First Name | string | true | null | 100 | `John` | Contact first name |
| `comm_contact_last_name` | Contact Last Name | string | true | null | 100 | `Smith` | Contact last name |
| `business_title` | Business Title | string | false | null | 100 | `Practice Owner` | Contact job title |
| `position` | Position | string | false | null | 50 | `DDS` | Professional designation |
| `comm_contact_email` | Contact Email | string | true | null | 255 | `john.smith@smiledental.com` | Contact email |
| `comm_contact_phone` | Contact Phone | string | true | null | 20 | `+1 (310) 555-1234` | Contact phone (E.164 format) |

#### **Business Type Section**

| field_name | label | data_type | is_required | default_value | example_value | description |
|------------|-------|-----------|-------------|---------------|---------------|-------------|
| `business_type` | Business Type | enum | false | `Corporation` | `Corporation` | Legal business structure |
| `company_status` | Company Status | enum | false | `Privately Held` | `Privately Held` | Public/private status |
| `stock_symbol` | Stock Symbol | string | false | null | `SMLE` | Stock ticker symbol (if public) |
| `stock_exchange` | Stock Exchange | enum | false | null | `NASDAQ` | Stock exchange (if public) |
| `business_identity` | Business Identity | string | false | null | `Healthcare Provider` | Business identity classification |
| `business_industry` | Business Industry | string | false | null | `Dental Practice` | Industry classification |

#### **Telecom Status Section**

| field_name | label | data_type | is_required | default_value | example_value | description |
|------------|-------|-----------|-------------|---------------|---------------|-------------|
| `telecom_status` | Telecom Status | enum | false | `pending` | `approved` | Telecom verification status (approved/pending/rejected) |
| `telecom_verified_at` | Verified At | timestamp | false | null | `2026-02-28T14:30:00Z` | Timestamp of verification |
| `telecom_verified_by` | Verified By | string | false | null | `admin@system` | User who verified |

### **Business Rules**

- `ein` must be encrypted at rest
- `comm_contact_phone` must be E.164 format for SMS compliance
- `telecom_status` triggers external API sync to SMS provider (Twilio/Bandwidth)
- Maximum 5 offices for Office-Specific Number (Twilio toll-free limit)
- Model office cannot be assigned to Multi-Office Shared Number
- Phone number assignment changes require telecom provider sync

### **Related Tables**

**Phone Number Assignment (office_phone_assignments)**

| field_name | data_type | description |
|------------|-----------|-------------|
| `id` | uuid | Primary key |
| `account_id` | uuid | Foreign key to accounts |
| `office_id` | uuid | Foreign key to offices |
| `assignment_type` | enum | `OFFICE_SPECIFIC` or `MULTI_OFFICE_SHARED` |
| `phone_number` | string | Assigned phone number |
| `created_at` | timestamp | Creation timestamp |

---

## TAB 5: ONLINE REGISTRATION

### **Field Definitions**

| field_name | label | data_type | is_required | default_value | max_length | example_value | description |
|------------|-------|-----------|-------------|---------------|------------|---------------|-------------|
| `id` | ID | uuid | true | auto-generated | 36 | `reg-001` | Primary key |
| `account_id` | Account ID | uuid | true | null | 36 | `acc-001` | Foreign key to accounts |
| `version_number` | Version Number | integer | true | 1 | - | 3 | Version number (increments on each save) |
| `header` | Header | string | true | null | 150 | `Patient Consent and Authorization` | Consent form header |
| `body_html` | Body HTML | text | true | null | 50000 | `<p>...</p>` | HTML consent form body (sanitized) |
| `is_active` | Is Active | boolean | true | true | - | true | Only one version active at a time |
| `effective_date` | Effective Date | timestamp | true | auto-generated | - | `2026-02-28T14:45:00Z` | When this version becomes active |
| `created_at` | Created At | timestamp | true | auto-generated | - | `2026-02-28T14:45:00Z` | Version creation timestamp |
| `created_by` | Created By | uuid | true | null | 36 | `user-001` | User who created version |
| `archived_at` | Archived At | timestamp | false | null | - | `2026-03-15T10:00:00Z` | When version was deactivated |

### **Business Rules**

- Only one version can have `is_active = true` at any time
- Saving creates new version and archives previous
- `body_html` must be sanitized to prevent XSS attacks
- `header` max length 150 characters
- Previously signed consent forms retain original version content (audit trail)
- New registrations use latest active version
- Versioning is immutable (cannot edit old versions)

### **Related Tables**

**Patient Consent Signatures (patient_consent_signatures)**

| field_name | data_type | description |
|------------|-----------|-------------|
| `id` | uuid | Primary key |
| `patient_id` | uuid | Foreign key to patients |
| `consent_version_id` | uuid | Foreign key to online_registration_consents |
| `signature_data` | text | Base64 encoded signature image |
| `ip_address` | string | IP address at time of signing |
| `user_agent` | string | Browser user agent |
| `signed_at` | timestamp | Signature timestamp |
| `consent_snapshot_html` | text | Full HTML snapshot at time of signing |

---

## DROPDOWN METADATA

### **US States** (`corporate_state`, `statement_state`, `comm_state`)

```json
{
  "field_name": "us_states",
  "is_multi_select": false,
  "options": [
    { "value": "AL", "label": "Alabama", "is_active": true },
    { "value": "AK", "label": "Alaska", "is_active": true },
    { "value": "AZ", "label": "Arizona", "is_active": true },
    { "value": "AR", "label": "Arkansas", "is_active": true },
    { "value": "CA", "label": "California", "is_active": true },
    { "value": "CO", "label": "Colorado", "is_active": true },
    { "value": "CT", "label": "Connecticut", "is_active": true },
    { "value": "DE", "label": "Delaware", "is_active": true },
    { "value": "FL", "label": "Florida", "is_active": true },
    { "value": "GA", "label": "Georgia", "is_active": true },
    { "value": "HI", "label": "Hawaii", "is_active": true },
    { "value": "ID", "label": "Idaho", "is_active": true },
    { "value": "IL", "label": "Illinois", "is_active": true },
    { "value": "IN", "label": "Indiana", "is_active": true },
    { "value": "IA", "label": "Iowa", "is_active": true },
    { "value": "KS", "label": "Kansas", "is_active": true },
    { "value": "KY", "label": "Kentucky", "is_active": true },
    { "value": "LA", "label": "Louisiana", "is_active": true },
    { "value": "ME", "label": "Maine", "is_active": true },
    { "value": "MD", "label": "Maryland", "is_active": true },
    { "value": "MA", "label": "Massachusetts", "is_active": true },
    { "value": "MI", "label": "Michigan", "is_active": true },
    { "value": "MN", "label": "Minnesota", "is_active": true },
    { "value": "MS", "label": "Mississippi", "is_active": true },
    { "value": "MO", "label": "Missouri", "is_active": true },
    { "value": "MT", "label": "Montana", "is_active": true },
    { "value": "NE", "label": "Nebraska", "is_active": true },
    { "value": "NV", "label": "Nevada", "is_active": true },
    { "value": "NH", "label": "New Hampshire", "is_active": true },
    { "value": "NJ", "label": "New Jersey", "is_active": true },
    { "value": "NM", "label": "New Mexico", "is_active": true },
    { "value": "NY", "label": "New York", "is_active": true },
    { "value": "NC", "label": "North Carolina", "is_active": true },
    { "value": "ND", "label": "North Dakota", "is_active": true },
    { "value": "OH", "label": "Ohio", "is_active": true },
    { "value": "OK", "label": "Oklahoma", "is_active": true },
    { "value": "OR", "label": "Oregon", "is_active": true },
    { "value": "PA", "label": "Pennsylvania", "is_active": true },
    { "value": "RI", "label": "Rhode Island", "is_active": true },
    { "value": "SC", "label": "South Carolina", "is_active": true },
    { "value": "SD", "label": "South Dakota", "is_active": true },
    { "value": "TN", "label": "Tennessee", "is_active": true },
    { "value": "TX", "label": "Texas", "is_active": true },
    { "value": "UT", "label": "Utah", "is_active": true },
    { "value": "VT", "label": "Vermont", "is_active": true },
    { "value": "VA", "label": "Virginia", "is_active": true },
    { "value": "WA", "label": "Washington", "is_active": true },
    { "value": "WV", "label": "West Virginia", "is_active": true },
    { "value": "WI", "label": "Wisconsin", "is_active": true },
    { "value": "WY", "label": "Wyoming", "is_active": true }
  ]
}
```

### **Culture Options** (`culture_code`)

```json
{
  "field_name": "culture_code",
  "is_multi_select": false,
  "options": [
    { "value": "en-US", "label": "English - United States", "is_active": true },
    { "value": "en-GB", "label": "English - United Kingdom", "is_active": true },
    { "value": "es-US", "label": "Spanish - United States", "is_active": true },
    { "value": "fr-CA", "label": "French - Canada", "is_active": true },
    { "value": "zh-CN", "label": "Chinese - Simplified", "is_active": true }
  ]
}
```

### **Ledger Color Options** (All color fields)

```json
{
  "field_name": "ledger_colors",
  "is_multi_select": false,
  "options": [
    { "value": "Blue", "label": "Blue", "hex": "#2563EB", "is_active": true },
    { "value": "Black", "label": "Black", "hex": "#000000", "is_active": true },
    { "value": "Aqua", "label": "Aqua", "hex": "#00FFFF", "is_active": true },
    { "value": "CadetBlue", "label": "Cadet Blue", "hex": "#5F9EA0", "is_active": true },
    { "value": "Chartreuse", "label": "Chartreuse", "hex": "#7FFF00", "is_active": true },
    { "value": "Chocolate", "label": "Chocolate", "hex": "#D2691E", "is_active": true },
    { "value": "Brown", "label": "Brown", "hex": "#A52A2A", "is_active": true },
    { "value": "OrangeRed", "label": "Orange Red", "hex": "#FF4500", "is_active": true },
    { "value": "DarkGray", "label": "Dark Gray", "hex": "#1F2937", "is_active": true },
    { "value": "Teal", "label": "Teal", "hex": "#0D9488", "is_active": true },
    { "value": "Purple", "label": "Purple", "hex": "#7C3AED", "is_active": true },
    { "value": "Green", "label": "Green", "hex": "#16A34A", "is_active": true },
    { "value": "Amber", "label": "Amber", "hex": "#D97706", "is_active": true },
    { "value": "LightGray", "label": "Light Gray", "hex": "#9CA3AF", "is_active": true },
    { "value": "Crimson", "label": "Crimson", "hex": "#DC143C", "is_active": true },
    { "value": "DarkGreen", "label": "Dark Green", "hex": "#006400", "is_active": true },
    { "value": "DarkOrange", "label": "Dark Orange", "hex": "#FF8C00", "is_active": true },
    { "value": "DeepPink", "label": "Deep Pink", "hex": "#FF1493", "is_active": true },
    { "value": "DodgerBlue", "label": "Dodger Blue", "hex": "#1E90FF", "is_active": true },
    { "value": "Fuchsia", "label": "Fuchsia", "hex": "#FF00FF", "is_active": true },
    { "value": "Gold", "label": "Gold", "hex": "#FFD700", "is_active": true },
    { "value": "Indigo", "label": "Indigo", "hex": "#4B0082", "is_active": true },
    { "value": "Maroon", "label": "Maroon", "hex": "#800000", "is_active": true },
    { "value": "Navy", "label": "Navy", "hex": "#000080", "is_active": true },
    { "value": "Olive", "label": "Olive", "hex": "#808000", "is_active": true },
    { "value": "Coral", "label": "Coral", "hex": "#FF7F50", "is_active": true }
  ]
}
```

### **Charting Option** (`charting_option`)

```json
{
  "field_name": "charting_option",
  "is_multi_select": false,
  "options": [
    { "value": "modal", "label": "Modal Style", "description": "Charting in modal overlay", "is_active": true },
    { "value": "submenu", "label": "Submenu Style", "description": "Charting in submenu panel", "is_active": true },
    { "value": "tabbed", "label": "Tabbed Style", "description": "Charting in tabbed interface", "is_active": true }
  ]
}
```

### **Default Charting Tab** (`default_charting_tab`)

```json
{
  "field_name": "default_charting_tab",
  "is_multi_select": false,
  "options": [
    { "value": "pre-existing", "label": "Pre-Existing", "is_active": true },
    { "value": "conditions", "label": "Conditions", "is_active": true },
    { "value": "treatment", "label": "Treatment", "is_active": true }
  ]
}
```

### **EDI Vendor** (`edi_vendor`)

```json
{
  "field_name": "edi_vendor",
  "is_multi_select": false,
  "options": [
    { "value": "nea", "label": "NEA", "is_active": true },
    { "value": "dentrix", "label": "Dentrix Ascend", "is_active": true },
    { "value": "healthicity", "label": "Healthicity", "is_active": true },
    { "value": "waystar", "label": "Waystar", "is_active": true }
  ]
}
```

### **Payment Portal Posting Office** (`payment_portal_posting_office`)

```json
{
  "field_name": "payment_portal_posting_office",
  "is_multi_select": false,
  "options": [
    { "value": "main", "label": "Main Office", "is_active": true },
    { "value": "branch1", "label": "Branch Office 1", "is_active": true },
    { "value": "branch2", "label": "Branch Office 2", "is_active": true }
  ],
  "note": "This should be dynamically populated from offices table"
}
```

### **Holiday Status** (`status`)

```json
{
  "field_name": "holiday_status",
  "is_multi_select": false,
  "options": [
    { "value": "CLOSED", "label": "Closed", "is_active": true },
    { "value": "OPEN", "label": "Open", "is_active": true },
    { "value": "HALF_DAY", "label": "Half Day", "is_active": true }
  ]
}
```

### **Holiday Type** (`holiday_type`)

```json
{
  "field_name": "holiday_type",
  "is_multi_select": false,
  "options": [
    { "value": "Federal", "label": "Federal", "is_active": true },
    { "value": "Custom", "label": "Custom", "is_active": true }
  ]
}
```

### **Business Type** (`business_type`)

```json
{
  "field_name": "business_type",
  "is_multi_select": false,
  "options": [
    { "value": "Sole Proprietorship", "label": "Sole Proprietorship", "is_active": true },
    { "value": "Partnership", "label": "Partnership", "is_active": true },
    { "value": "LLC", "label": "Limited Liability Company (LLC)", "is_active": true },
    { "value": "Corporation", "label": "Corporation", "is_active": true },
    { "value": "S-Corporation", "label": "S-Corporation", "is_active": true },
    { "value": "Non-Profit", "label": "Non-Profit Organization", "is_active": true }
  ]
}
```

### **Company Status** (`company_status`)

```json
{
  "field_name": "company_status",
  "is_multi_select": false,
  "options": [
    { "value": "Privately Held", "label": "Privately Held", "is_active": true },
    { "value": "Publicly Traded", "label": "Publicly Traded", "is_active": true }
  ]
}
```

### **Stock Exchange** (`stock_exchange`)

```json
{
  "field_name": "stock_exchange",
  "is_multi_select": false,
  "options": [
    { "value": "NYSE", "label": "New York Stock Exchange (NYSE)", "is_active": true },
    { "value": "NASDAQ", "label": "NASDAQ", "is_active": true },
    { "value": "AMEX", "label": "American Stock Exchange (AMEX)", "is_active": true }
  ]
}
```

### **Telecom Status** (`telecom_status`)

```json
{
  "field_name": "telecom_status",
  "is_multi_select": false,
  "options": [
    { "value": "pending", "label": "Pending Verification", "is_active": true },
    { "value": "approved", "label": "Approved", "is_active": true },
    { "value": "rejected", "label": "Rejected", "is_active": true }
  ]
}
```

### **Phone Assignment Type** (`assignment_type`)

```json
{
  "field_name": "phone_assignment_type",
  "is_multi_select": false,
  "options": [
    { "value": "OFFICE_SPECIFIC", "label": "Office-Specific Number", "description": "Dedicated phone number per office (max 5)", "is_active": true },
    { "value": "MULTI_OFFICE_SHARED", "label": "Multi-Office Shared Number", "description": "Shared phone number across multiple offices", "is_active": true }
  ]
}
```

---

## DATABASE DESIGN

### **Suggested Table Structure**

#### **1. `accounts` (Main Table - Tab 1: Basic + Tab 2: Advanced)**

```sql
CREATE TABLE accounts (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Basic Tab Fields
  account_number VARCHAR(20) UNIQUE NOT NULL,
  account_name VARCHAR(200) NOT NULL,
  account_short_id VARCHAR(50) UNIQUE NOT NULL,
  contact_first_name VARCHAR(100),
  contact_last_name VARCHAR(100),
  corporate_address VARCHAR(500),
  corporate_city VARCHAR(100),
  corporate_state VARCHAR(2),
  corporate_zip VARCHAR(10),
  statement_address VARCHAR(500),
  statement_city VARCHAR(100),
  statement_state VARCHAR(2),
  statement_zip VARCHAR(10),
  email VARCHAR(255) NOT NULL,
  phone VARCHAR(20),
  phone_2 VARCHAR(20),
  culture_code VARCHAR(10) DEFAULT 'en-US',
  logo_url TEXT,
  custom_1 VARCHAR(500),
  custom_2 VARCHAR(500),
  
  -- Advanced Tab - Ledger Colors
  procedure_color VARCHAR(50) DEFAULT 'DarkGray',
  insurance_payment_color VARCHAR(50) DEFAULT 'Teal',
  claim_lines_color VARCHAR(50) DEFAULT 'Purple',
  patient_payment_color VARCHAR(50) DEFAULT 'Green',
  adjustment_color VARCHAR(50) DEFAULT 'Amber',
  statement_lines_color VARCHAR(50) DEFAULT 'Blue',
  notes_lines_color VARCHAR(50) DEFAULT 'LightGray',
  
  -- Advanced Tab - Options
  enable_full_screen BOOLEAN DEFAULT FALSE,
  max_treatment_plan_discount DECIMAL(5,2) DEFAULT 0.00,
  only_show_office_items BOOLEAN DEFAULT FALSE,
  statement_close_out_individual BOOLEAN DEFAULT FALSE,
  auto_post_periodic_charges BOOLEAN DEFAULT FALSE,
  show_flash_alerts_insurance BOOLEAN DEFAULT FALSE,
  pronoun_field_visible BOOLEAN DEFAULT FALSE,
  
  -- Advanced Tab - Default Settings
  charting_option VARCHAR(20) DEFAULT 'modal',
  default_charting_tab VARCHAR(20) DEFAULT 'treatment',
  password_expiration_days INTEGER DEFAULT 90,
  scheduler_show_non_working_days BOOLEAN DEFAULT FALSE,
  default_fee_increase_code VARCHAR(50),
  default_write_off_code VARCHAR(50),
  
  -- Advanced Tab - Required Fields
  patient_dob_required BOOLEAN DEFAULT FALSE,
  patient_ssn_required BOOLEAN DEFAULT FALSE,
  patient_email_required BOOLEAN DEFAULT FALSE,
  patient_phone_required BOOLEAN DEFAULT FALSE,
  patient_address_required BOOLEAN DEFAULT FALSE,
  responsible_party_required BOOLEAN DEFAULT FALSE,
  
  -- Advanced Tab - Third Party Settings
  edi_vendor VARCHAR(50),
  transworld_enabled BOOLEAN DEFAULT FALSE,
  xvweb_enabled BOOLEAN DEFAULT FALSE,
  cloud9_enabled BOOLEAN DEFAULT FALSE,
  
  -- Advanced Tab - Payment Portal
  payment_portal_posting_office VARCHAR(50),
  post_payment_to_responsible_party BOOLEAN DEFAULT FALSE,
  
  -- Advanced Tab - AI Assist
  ai_assist_org_id VARCHAR(100),
  ai_assist_client_id VARCHAR(100),
  ai_assist_client_secret TEXT, -- Encrypted
  
  -- Global Metadata
  pgid VARCHAR(50),
  oid VARCHAR(50),
  status VARCHAR(20) DEFAULT 'active',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_by UUID,
  updated_by UUID,
  
  -- Constraints
  CONSTRAINT check_max_discount CHECK (max_treatment_plan_discount >= 0 AND max_treatment_plan_discount <= 100),
  CONSTRAINT check_password_expiration CHECK (password_expiration_days >= 0 AND password_expiration_days <= 365),
  CONSTRAINT check_email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

-- Indexes
CREATE INDEX idx_accounts_account_number ON accounts(account_number);
CREATE INDEX idx_accounts_account_short_id ON accounts(account_short_id);
CREATE INDEX idx_accounts_email ON accounts(email);
CREATE INDEX idx_accounts_status ON accounts(status);
```

#### **2. `account_holidays` (Tab 3: Holidays)**

```sql
CREATE TABLE account_holidays (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Foreign Key
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  
  -- Holiday Fields
  holiday_date DATE NOT NULL,
  holiday_name VARCHAR(200) NOT NULL,
  status VARCHAR(20) DEFAULT 'CLOSED',
  holiday_type VARCHAR(20) DEFAULT 'Custom',
  is_recurring BOOLEAN DEFAULT FALSE,
  
  -- Global Metadata
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_by UUID,
  updated_by UUID,
  
  -- Constraints
  CONSTRAINT check_holiday_status CHECK (status IN ('CLOSED', 'OPEN', 'HALF_DAY')),
  CONSTRAINT check_holiday_type CHECK (holiday_type IN ('Federal', 'Custom'))
);

-- Indexes
CREATE INDEX idx_holidays_account_id ON account_holidays(account_id);
CREATE INDEX idx_holidays_date ON account_holidays(holiday_date);
CREATE INDEX idx_holidays_recurring ON account_holidays(is_recurring);
CREATE UNIQUE INDEX idx_holidays_unique_date ON account_holidays(account_id, holiday_date);
```

#### **3. `account_communications` (Tab 4: Communications)**

```sql
CREATE TABLE account_communications (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Foreign Key (One-to-One with accounts)
  account_id UUID UNIQUE NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  
  -- Business Information
  business_name VARCHAR(200) NOT NULL,
  region_of_operations VARCHAR(100) NOT NULL,
  country VARCHAR(100) NOT NULL,
  comm_address_line_1 VARCHAR(500) NOT NULL,
  comm_city VARCHAR(100) NOT NULL,
  comm_state VARCHAR(2) NOT NULL,
  comm_zip VARCHAR(10) NOT NULL,
  ein TEXT, -- Encrypted
  website VARCHAR(500) NOT NULL,
  
  -- Business Contact
  comm_contact_first_name VARCHAR(100) NOT NULL,
  comm_contact_last_name VARCHAR(100) NOT NULL,
  business_title VARCHAR(100),
  position VARCHAR(50),
  comm_contact_email VARCHAR(255) NOT NULL,
  comm_contact_phone VARCHAR(20) NOT NULL,
  
  -- Business Type
  business_type VARCHAR(50) DEFAULT 'Corporation',
  company_status VARCHAR(50) DEFAULT 'Privately Held',
  stock_symbol VARCHAR(10),
  stock_exchange VARCHAR(20),
  business_identity VARCHAR(100),
  business_industry VARCHAR(100),
  
  -- Telecom Status
  telecom_status VARCHAR(20) DEFAULT 'pending',
  telecom_verified_at TIMESTAMP,
  telecom_verified_by VARCHAR(255),
  
  -- Global Metadata
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_by UUID,
  updated_by UUID,
  
  -- Constraints
  CONSTRAINT check_telecom_status CHECK (telecom_status IN ('pending', 'approved', 'rejected')),
  CONSTRAINT check_company_status CHECK (company_status IN ('Privately Held', 'Publicly Traded'))
);

-- Indexes
CREATE INDEX idx_comm_account_id ON account_communications(account_id);
CREATE INDEX idx_comm_telecom_status ON account_communications(telecom_status);
```

#### **4. `office_phone_assignments` (Tab 4: Phone Number Assignment)**

```sql
CREATE TABLE office_phone_assignments (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Foreign Keys
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  office_id UUID NOT NULL REFERENCES offices(id) ON DELETE CASCADE,
  
  -- Assignment Fields
  assignment_type VARCHAR(30) NOT NULL,
  phone_number VARCHAR(20),
  is_model_office BOOLEAN DEFAULT FALSE,
  
  -- Global Metadata
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  -- Constraints
  CONSTRAINT check_assignment_type CHECK (assignment_type IN ('OFFICE_SPECIFIC', 'MULTI_OFFICE_SHARED'))
);

-- Indexes
CREATE INDEX idx_phone_assign_account ON office_phone_assignments(account_id);
CREATE INDEX idx_phone_assign_office ON office_phone_assignments(office_id);
CREATE INDEX idx_phone_assign_type ON office_phone_assignments(assignment_type);

-- Business rule: Max 5 offices for OFFICE_SPECIFIC
-- Enforced at application level or via trigger
```

#### **5. `online_registration_consents` (Tab 5: Online Registration)**

```sql
CREATE TABLE online_registration_consents (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Foreign Key
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  
  -- Consent Fields
  version_number INTEGER NOT NULL,
  header VARCHAR(150) NOT NULL,
  body_html TEXT NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  effective_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  
  -- Global Metadata
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_by UUID NOT NULL,
  archived_at TIMESTAMP,
  
  -- Constraints
  CONSTRAINT check_version_positive CHECK (version_number > 0),
  CONSTRAINT check_header_length CHECK (LENGTH(header) <= 150)
);

-- Indexes
CREATE INDEX idx_consent_account_id ON online_registration_consents(account_id);
CREATE INDEX idx_consent_active ON online_registration_consents(is_active);
CREATE INDEX idx_consent_version ON online_registration_consents(account_id, version_number);

-- Unique constraint: Only one active version per account
CREATE UNIQUE INDEX idx_consent_unique_active ON online_registration_consents(account_id, is_active) WHERE is_active = TRUE;
```

#### **6. `patient_consent_signatures` (Related to Tab 5)**

```sql
CREATE TABLE patient_consent_signatures (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Foreign Keys
  patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  consent_version_id UUID NOT NULL REFERENCES online_registration_consents(id),
  
  -- Signature Fields
  signature_data TEXT NOT NULL, -- Base64 encoded signature
  ip_address VARCHAR(50),
  user_agent TEXT,
  signed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  consent_snapshot_html TEXT NOT NULL, -- Full HTML at time of signing
  
  -- Global Metadata
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_consent_sig_patient ON patient_consent_signatures(patient_id);
CREATE INDEX idx_consent_sig_version ON patient_consent_signatures(consent_version_id);
CREATE INDEX idx_consent_sig_date ON patient_consent_signatures(signed_at);
```

#### **7. `lookup_colors` (Lookup Table for Ledger Colors)**

```sql
CREATE TABLE lookup_colors (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  color_name VARCHAR(50) UNIQUE NOT NULL,
  color_label VARCHAR(100) NOT NULL,
  hex_value VARCHAR(7) NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  sort_order INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pre-populate with 26 color options from UI
INSERT INTO lookup_colors (color_name, color_label, hex_value, sort_order) VALUES
  ('Blue', 'Blue', '#2563EB', 1),
  ('Black', 'Black', '#000000', 2),
  ('Aqua', 'Aqua', '#00FFFF', 3),
  -- ... (all 26 colors)
  ('Coral', 'Coral', '#FF7F50', 26);
```

---

## NORMALIZATION RECOMMENDATIONS

### **Normalize Dropdown Data**

Instead of hardcoding dropdown values in application code, create lookup tables:

```sql
-- States
CREATE TABLE lookup_states (
  code VARCHAR(2) PRIMARY KEY,
  name VARCHAR(50) NOT NULL,
  is_active BOOLEAN DEFAULT TRUE
);

-- Cultures
CREATE TABLE lookup_cultures (
  code VARCHAR(10) PRIMARY KEY,
  label VARCHAR(100) NOT NULL,
  is_active BOOLEAN DEFAULT TRUE
);

-- EDI Vendors
CREATE TABLE lookup_edi_vendors (
  code VARCHAR(50) PRIMARY KEY,
  label VARCHAR(100) NOT NULL,
  is_active BOOLEAN DEFAULT TRUE
);

-- Business Types
CREATE TABLE lookup_business_types (
  code VARCHAR(50) PRIMARY KEY,
  label VARCHAR(100) NOT NULL,
  is_active BOOLEAN DEFAULT TRUE
);

-- Stock Exchanges
CREATE TABLE lookup_stock_exchanges (
  code VARCHAR(20) PRIMARY KEY,
  label VARCHAR(100) NOT NULL,
  is_active BOOLEAN DEFAULT TRUE
);

-- Charting Options
CREATE TABLE lookup_charting_options (
  code VARCHAR(20) PRIMARY KEY,
  label VARCHAR(100) NOT NULL,
  description TEXT,
  is_active BOOLEAN DEFAULT TRUE
);

-- Charting Tabs
CREATE TABLE lookup_charting_tabs (
  code VARCHAR(20) PRIMARY KEY,
  label VARCHAR(100) NOT NULL,
  is_active BOOLEAN DEFAULT TRUE
);
```

### **Add Foreign Keys for Normalized Data**

```sql
ALTER TABLE accounts 
  ADD CONSTRAINT fk_corporate_state FOREIGN KEY (corporate_state) REFERENCES lookup_states(code),
  ADD CONSTRAINT fk_statement_state FOREIGN KEY (statement_state) REFERENCES lookup_states(code),
  ADD CONSTRAINT fk_culture_code FOREIGN KEY (culture_code) REFERENCES lookup_cultures(code),
  ADD CONSTRAINT fk_edi_vendor FOREIGN KEY (edi_vendor) REFERENCES lookup_edi_vendors(code),
  ADD CONSTRAINT fk_charting_option FOREIGN KEY (charting_option) REFERENCES lookup_charting_options(code),
  ADD CONSTRAINT fk_default_charting_tab FOREIGN KEY (default_charting_tab) REFERENCES lookup_charting_tabs(code);

ALTER TABLE account_communications
  ADD CONSTRAINT fk_comm_state FOREIGN KEY (comm_state) REFERENCES lookup_states(code),
  ADD CONSTRAINT fk_business_type FOREIGN KEY (business_type) REFERENCES lookup_business_types(code),
  ADD CONSTRAINT fk_stock_exchange FOREIGN KEY (stock_exchange) REFERENCES lookup_stock_exchanges(code);
```

---

## API ENDPOINTS

### **Tab 1: Basic**

```
GET    /api/accounts/:id                      # Get account details
PUT    /api/accounts/:id                      # Update account
POST   /api/accounts/:id/logo                 # Upload logo
DELETE /api/accounts/:id/logo                 # Delete logo
```

### **Tab 2: Advanced**

```
PUT    /api/accounts/:id/advanced-settings    # Update advanced settings
GET    /api/accounts/:id/advanced-settings    # Get advanced settings
GET    /api/lookup/colors                     # Get available colors
GET    /api/lookup/charting-options           # Get charting options
GET    /api/lookup/edi-vendors                # Get EDI vendors
```

### **Tab 3: Holidays**

```
GET    /api/accounts/:accountId/holidays      # List holidays
POST   /api/accounts/:accountId/holidays      # Add holiday
PUT    /api/accounts/:accountId/holidays/:id  # Update holiday
DELETE /api/accounts/:accountId/holidays/:id  # Delete holiday
DELETE /api/accounts/:accountId/holidays      # Bulk delete (body: {ids: []})
POST   /api/accounts/:accountId/holidays/federal  # Import federal holidays (body: {year: 2026})
POST   /api/accounts/:accountId/holidays/range    # Add date range (body: {fromDate, toDate, name})
```

### **Tab 4: Communications**

```
GET    /api/accounts/:accountId/communications     # Get communication settings
PUT    /api/accounts/:accountId/communications     # Update communication settings
POST   /api/accounts/:accountId/communications/verify-telecom  # Trigger telecom verification
GET    /api/accounts/:accountId/phone-assignments  # Get phone number assignments
PUT    /api/accounts/:accountId/phone-assignments  # Update phone assignments
```

### **Tab 5: Online Registration**

```
GET    /api/accounts/:accountId/consents           # Get all consent versions
GET    /api/accounts/:accountId/consents/active    # Get active consent version
POST   /api/accounts/:accountId/consents           # Create new consent version (auto-archives old)
GET    /api/accounts/:accountId/consents/:id       # Get specific consent version
GET    /api/accounts/:accountId/consents/:id/pdf   # Generate PDF export
GET    /api/accounts/:accountId/consents/:id/preview  # Preview patient view
```

### **Lookup Data Endpoints**

```
GET    /api/lookup/states                     # US states
GET    /api/lookup/cultures                   # Culture codes
GET    /api/lookup/colors                     # Ledger colors
GET    /api/lookup/charting-options           # Charting options
GET    /api/lookup/charting-tabs              # Charting tabs
GET    /api/lookup/edi-vendors                # EDI vendors
GET    /api/lookup/business-types             # Business types
GET    /api/lookup/stock-exchanges            # Stock exchanges
GET    /api/lookup/offices?accountId=:id      # Offices for payment portal dropdown
```

---

## VALIDATION RULES

### **Basic Tab**

| Field | Validation Rules |
|-------|-----------------|
| `account_name` | Required, 1-200 characters |
| `account_short_id` | Required, 1-50 characters, lowercase, alphanumeric + hyphens only, unique |
| `email` | Required, valid RFC 5322 email format, unique |
| `corporate_zip` | Optional, 5 or 9 digits (e.g., `12345` or `12345-6789`) |
| `statement_zip` | Optional, 5 or 9 digits |
| `phone` | Optional, E.164 format recommended (e.g., `+14155551234`) |
| `logo_url` | Optional, image/jpeg or image/png, max 2MB |

### **Advanced Tab**

| Field | Validation Rules |
|-------|-----------------|
| `max_treatment_plan_discount` | 0 <= value <= 100 |
| `password_expiration_days` | 0 <= value <= 365 |
| `default_fee_increase_code` | Optional, alphanumeric + hyphens |
| `default_write_off_code` | Optional, alphanumeric + hyphens |
| `ai_assist_client_secret` | Encrypted before storage, never returned in GET |

### **Holidays Tab**

| Field | Validation Rules |
|-------|-----------------|
| `holiday_name` | Required, 1-200 characters |
| `holiday_date` | Required, valid date (YYYY-MM-DD), cannot be in the past |
| Unique constraint | One holiday per date per account |

### **Communications Tab**

| Field | Validation Rules |
|-------|-----------------|
| `business_name` | Required, 1-200 characters |
| `country` | Required |
| `comm_address_line_1` | Required, 1-500 characters |
| `comm_city` | Required, 1-100 characters |
| `comm_state` | Required, valid state code |
| `comm_zip` | Required, 5 or 9 digits |
| `website` | Required, valid URL format |
| `comm_contact_email` | Required, valid email format |
| `comm_contact_phone` | Required, E.164 format |
| `ein` | Optional, encrypted before storage, format XX-XXXXXXX |
| Office-Specific assignments | Max 5 offices (Twilio limit) |
| Model office | Cannot be assigned to Multi-Office Shared |

### **Online Registration Tab**

| Field | Validation Rules |
|-------|-----------------|
| `header` | Required, 1-150 characters |
| `body_html` | Required, sanitized to prevent XSS |
| `version_number` | Auto-incremented, unique per account |
| `is_active` | Only one active version per account |

---

## SECURITY CONSIDERATIONS

### **Encrypted Fields**

These fields must be encrypted at rest:

- `ein` (Employer Identification Number)
- `ai_assist_client_secret` (AI service credentials)

**Encryption Method:** AES-256-GCM or use database-level encryption (e.g., PostgreSQL `pgcrypto`)

**Key Management:** Store encryption keys in secrets manager (AWS Secrets Manager, Azure Key Vault, HashiCorp Vault)

### **Sensitive Data Masking**

When returning data to frontend:

- `ein`: Return masked as `XX-XXX1234` (show last 4 digits only)
- `ai_assist_client_secret`: Never return, show as `••••••••••`

### **Access Control**

**Communications Tab & Online Registration Tab:**
- Restrict to Super Admin and Account Owner roles only
- Log all changes with `created_by` / `updated_by` audit trail

**Logo Upload:**
- Validate file type (JPEG/PNG only)
- Validate file size (max 2MB)
- Scan for malware before storage
- Store in CDN (S3/CloudFront) with signed URLs

**HTML Sanitization:**
- `body_html` must be sanitized to prevent XSS
- Use libraries like DOMPurify or Bleach
- Whitelist allowed HTML tags: `<p>`, `<ul>`, `<li>`, `<strong>`, `<em>`, `<br>`, `<h1-h6>`

---

## AUDIT TRAIL

### **Global Metadata Fields (All Tables)**

| field_name | data_type | description |
|------------|-----------|-------------|
| `id` | uuid | Primary key |
| `created_at` | timestamp | Record creation timestamp (UTC) |
| `updated_at` | timestamp | Last update timestamp (UTC) |
| `created_by` | uuid | User ID who created record |
| `updated_by` | uuid | User ID who last updated record |
| `status` | enum | Record status (`active`, `inactive`, `deleted`) |

### **Version Control (Online Registration)**

- Each consent form save creates a new version
- Old versions are archived (`archived_at` timestamp set)
- Patient signatures link to specific version via `consent_version_id`
- Immutable audit trail for legal compliance

### **Change Log Table (Optional)**

```sql
CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  table_name VARCHAR(100) NOT NULL,
  record_id UUID NOT NULL,
  action VARCHAR(20) NOT NULL, -- INSERT, UPDATE, DELETE
  changed_fields JSONB, -- Old vs new values
  changed_by UUID NOT NULL,
  changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  ip_address VARCHAR(50),
  user_agent TEXT
);
```

---

## MIGRATION STRATEGY

### **Phase 1: Create Tables**
1. Create lookup tables first
2. Create `accounts` table
3. Create dependent tables (`account_holidays`, `account_communications`, etc.)

### **Phase 2: Migrate Data**
1. Import existing account data into `accounts` table
2. Generate `account_number` for existing records
3. Encrypt sensitive fields (`ein`, `ai_assist_client_secret`)

### **Phase 3: Create Indexes**
1. Create all indexes for performance
2. Create unique constraints

### **Phase 4: Add Foreign Keys**
1. Add foreign key constraints to ensure referential integrity

### **Phase 5: Triggers (Optional)**
1. Auto-update `updated_at` timestamp on UPDATE
2. Enforce business rules (e.g., max 5 offices for Office-Specific)

---

## PERFORMANCE OPTIMIZATIONS

### **Indexes**
- Created on all foreign keys
- Created on frequently queried fields (`account_number`, `account_short_id`, `email`)
- Composite indexes for common queries

### **Partitioning**
- Consider partitioning `audit_log` table by date for large datasets

### **Caching**
- Cache lookup tables in Redis (states, colors, etc.)
- Cache account settings per account ID
- Invalidate cache on UPDATE

### **Query Optimization**
- Use `SELECT` specific columns instead of `SELECT *`
- Use pagination for holiday listings
- Use `EXPLAIN ANALYZE` to optimize slow queries

---

## TESTING CHECKLIST

### **Unit Tests**
- [ ] Validate email format
- [ ] Validate ZIP code format (5 or 9 digits)
- [ ] Validate `account_short_id` (lowercase, alphanumeric + hyphens)
- [ ] Validate max treatment plan discount (0-100)
- [ ] Validate password expiration days (0-365)
- [ ] Validate logo file size (max 2MB)
- [ ] Validate logo file type (JPEG/PNG)
- [ ] Sanitize HTML in consent body

### **Integration Tests**
- [ ] Create account
- [ ] Update account
- [ ] Upload logo
- [ ] Add holiday
- [ ] Bulk delete holidays
- [ ] Import federal holidays
- [ ] Update communication settings
- [ ] Verify telecom status sync
- [ ] Create new consent version
- [ ] Deactivate old consent version
- [ ] Sign consent form (patient)

### **Business Logic Tests**
- [ ] Only one active consent version per account
- [ ] Max 5 offices for Office-Specific phone assignment
- [ ] Model office cannot be Multi-Office Shared
- [ ] Password expiration 0 = never expire
- [ ] Consent version auto-increment
- [ ] Holiday date cannot be duplicate per account

### **Security Tests**
- [ ] EIN is encrypted in database
- [ ] AI client secret is encrypted in database
- [ ] EIN returns masked value in API
- [ ] AI client secret never returns in API
- [ ] HTML sanitization prevents XSS
- [ ] Logo upload validates file type
- [ ] Logo upload validates file size

---

## EXAMPLE API REQUEST/RESPONSE

### **GET /api/accounts/:id**

**Response:**
```json
{
  "id": "acc-001",
  "account_number": "100123",
  "account_name": "Smile Bright Dental Group",
  "account_short_id": "smilebright",
  "contact_first_name": "Sarah",
  "contact_last_name": "Johnson",
  "email": "billing@smilebright.com",
  "phone": "(415) 555-1234",
  "culture_code": "en-US",
  "logo_url": "https://cdn.example.com/logos/acc-001.png",
  "procedure_color": "DarkGray",
  "enable_full_screen": true,
  "max_treatment_plan_discount": 15.50,
  "charting_option": "modal",
  "edi_vendor": "nea",
  "pgid": "PG-5001",
  "oid": "OFF-101",
  "updated_at": "2026-02-28T10:45:00Z",
  "updated_by": "admin@smilebright.com"
}
```

### **PUT /api/accounts/:id**

**Request:**
```json
{
  "account_name": "Smile Bright Dental Group - Updated",
  "email": "newemail@smilebright.com",
  "max_treatment_plan_discount": 20.0
}
```

**Response:**
```json
{
  "success": true,
  "message": "Account updated successfully",
  "data": {
    "id": "acc-001",
    "account_name": "Smile Bright Dental Group - Updated",
    "email": "newemail@smilebright.com",
    "updated_at": "2026-05-03T14:30:00Z"
  }
}
```

### **POST /api/accounts/:accountId/holidays**

**Request:**
```json
{
  "holiday_date": "2026-12-31",
  "holiday_name": "New Year's Eve",
  "status": "HALF_DAY",
  "holiday_type": "Custom",
  "is_recurring": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Holiday added successfully",
  "data": {
    "id": "hol-123",
    "account_id": "acc-001",
    "holiday_date": "2026-12-31",
    "holiday_name": "New Year's Eve",
    "status": "HALF_DAY",
    "holiday_type": "Custom",
    "is_recurring": true,
    "created_at": "2026-05-03T14:35:00Z"
  }
}
```

### **POST /api/accounts/:accountId/consents**

**Request:**
```json
{
  "header": "Patient Consent and Authorization v2",
  "body_html": "<p><strong>Updated HIPAA Notice...</strong></p>"
}
```

**Response:**
```json
{
  "success": true,
  "message": "New consent version created. Previous version archived.",
  "data": {
    "id": "consent-456",
    "account_id": "acc-001",
    "version_number": 4,
    "header": "Patient Consent and Authorization v2",
    "is_active": true,
    "effective_date": "2026-05-03T14:40:00Z",
    "created_by": "user-001"
  }
}
```

---

## SUMMARY

This data definition document provides:

✅ **Complete field definitions** for all 5 tabs  
✅ **Dropdown metadata** with all allowed values  
✅ **Database schema** with tables, indexes, constraints  
✅ **API endpoints** for CRUD operations  
✅ **Validation rules** for all fields  
✅ **Security considerations** for encrypted/sensitive data  
✅ **Normalization recommendations** for lookup tables  
✅ **Audit trail** with global metadata fields  
✅ **Business logic** enforcement  
✅ **Migration strategy** for existing data  
✅ **Performance optimizations** (indexes, caching)  
✅ **Testing checklist** for QA  

**Ready for:**
- SQL schema generation
- Backend API development
- Frontend form validation
- Data migration scripts
- Documentation for developers

---

**Document Version:** 1.0  
**Last Updated:** May 3, 2026  
**Author:** AI Assistant  
**Status:** Production-Ready
