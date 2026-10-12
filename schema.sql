--
-- PostgreSQL database dump
--

\restrict xv8v52yaMyBvp4FxRamNxYKB9bEITvRvC5EpBjrvASJG8jXSUTUu2mgfIyyAdbC

-- Dumped from database version 15.18
-- Dumped by pg_dump version 18.1

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

-- *not* creating schema, since initdb creates it


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS '';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: account_communications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.account_communications (
    tenant_id integer NOT NULL,
    comm_number_type character varying(20),
    business_name character varying(255),
    region_of_operations character varying(255),
    comm_country character varying(2) NOT NULL,
    comm_address_1 character varying(255),
    comm_address_2 character varying(255),
    comm_city character varying(100),
    comm_state character varying(50),
    comm_zip character varying(20),
    ein_enc text,
    website character varying(500),
    comm_contact_first_name character varying(100),
    comm_contact_last_name character varying(100),
    business_title character varying(100),
    "position" character varying(100),
    comm_contact_email character varying(255),
    comm_contact_phone character varying(20),
    business_type character varying(50),
    company_status character varying(50),
    stock_symbol character varying(20),
    stock_exchange character varying(50),
    business_identity character varying(255),
    business_industry character varying(100),
    telecom_status character varying(30),
    telecom_verified_at timestamp without time zone,
    telecom_verified_by integer,
    updated_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    messaging_service_sid character varying(40),
    sms_from_phone character varying(20),
    sms_quiet_hours_start integer DEFAULT 8 NOT NULL,
    sms_quiet_hours_end integer DEFAULT 21 NOT NULL,
    sms_reminders_enabled boolean DEFAULT false NOT NULL,
    sms_reminder_lead_hours json,
    sms_reminder_template_id integer
);


--
-- Name: account_communications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.account_communications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: account_communications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.account_communications_id_seq OWNED BY public.account_communications.id;


--
-- Name: account_consents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.account_consents (
    tenant_id integer NOT NULL,
    version_number integer NOT NULL,
    header character varying(500) NOT NULL,
    body_html text NOT NULL,
    is_active boolean NOT NULL,
    effective_date date,
    created_by integer,
    archived_at timestamp without time zone,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: account_consents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.account_consents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: account_consents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.account_consents_id_seq OWNED BY public.account_consents.id;


--
-- Name: account_holidays; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.account_holidays (
    tenant_id integer NOT NULL,
    holiday_date date NOT NULL,
    holiday_name character varying(255) NOT NULL,
    status character varying(20),
    holiday_type character varying(20),
    is_recurring boolean NOT NULL,
    created_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    office_id integer
);


--
-- Name: account_holidays_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.account_holidays_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: account_holidays_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.account_holidays_id_seq OWNED BY public.account_holidays.id;


--
-- Name: account_notes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.account_notes (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    legacy_id character varying(20),
    note_type character varying(10),
    notes text NOT NULL,
    is_struck_off boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer
);


--
-- Name: account_notes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.account_notes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: account_notes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.account_notes_id_seq OWNED BY public.account_notes.id;


--
-- Name: account_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.account_settings (
    tenant_id integer NOT NULL,
    contact_first_name character varying(100),
    contact_last_name character varying(100),
    corporate_address_1 character varying(255),
    corporate_address_2 character varying(255),
    corporate_city character varying(100),
    corporate_state character varying(50),
    corporate_zip character varying(20),
    email character varying(255),
    phone character varying(20),
    phone_2 character varying(20),
    culture_code character varying(20) NOT NULL,
    custom_1 character varying(255),
    custom_2 character varying(255),
    pgid character varying(50),
    oid character varying(50),
    logo_url character varying(500),
    statement_use_corporate boolean NOT NULL,
    statement_address_1 character varying(255),
    statement_address_2 character varying(255),
    statement_city character varying(100),
    statement_state character varying(50),
    statement_zip character varying(20),
    statement_phone character varying(20),
    theme character varying(50),
    enable_full_screen boolean NOT NULL,
    ortho_claim_fee_mode character varying(50),
    ortho_visit_code character varying(20),
    max_treatment_plan_discount numeric(5,2),
    treatment_plan_discount_code character varying(50),
    per_visit_copay_code character varying(50),
    only_show_office_items boolean NOT NULL,
    statement_close_out_individual boolean NOT NULL,
    statement_close_out_all boolean NOT NULL,
    show_booked_production boolean NOT NULL,
    auto_post_periodic_charges boolean NOT NULL,
    show_flash_alerts_insurance boolean NOT NULL,
    pronoun_field_visible character varying(10),
    procedure_color character varying(50),
    insurance_payment_color character varying(50),
    claim_lines_color character varying(50),
    patient_payment_color character varying(50),
    adjustment_color character varying(50),
    statement_lines_color character varying(50),
    notes_lines_color character varying(50),
    charting_option character varying(50),
    default_charting_tab character varying(50),
    show_production_colors boolean NOT NULL,
    model_office_id integer,
    default_treatment_plan_filter character varying(50),
    credit_ins_overpayment_to_patient boolean NOT NULL,
    password_expiration_days integer NOT NULL,
    scheduler_show_non_working_days boolean NOT NULL,
    email_receipts_to_patients boolean NOT NULL,
    default_fee_increase_code character varying(50),
    default_fee_decrease_code character varying(50),
    default_transfer_code character varying(50),
    default_write_off_code character varying(50),
    phone_required_mode character varying(20),
    dob_required_mode character varying(20),
    ssn_required_mode character varying(20),
    email_required boolean NOT NULL,
    edi_vendor character varying(50),
    transfirst_auto_recurring boolean NOT NULL,
    transworld_all_offices boolean NOT NULL,
    transworld_office_id integer,
    transworld_portal_url character varying(500),
    xvweb_url character varying(500),
    cloud9_url character varying(500),
    auto_eligibility boolean NOT NULL,
    payment_portal_posting_office character varying(50),
    payment_portal_post_to_rp boolean NOT NULL,
    use_planet_dds_pay boolean NOT NULL,
    ai_assist_org_id character varying(100),
    ai_assist_client_id character varying(255),
    ai_assist_client_secret_enc text,
    updated_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    marketing_name character varying(255),
    marketing_address_1 character varying(255),
    marketing_address_2 character varying(255),
    marketing_city character varying(100),
    marketing_state character varying(50),
    marketing_zip character varying(20),
    marketing_phone character varying(20)
);


--
-- Name: account_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.account_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: account_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.account_settings_id_seq OWNED BY public.account_settings.id;


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: appointment_procedures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.appointment_procedures (
    id integer NOT NULL,
    appointment_id character varying(50) NOT NULL,
    procedure_code character varying(20) NOT NULL,
    provider_id character varying(50),
    treatment_plan_id character varying(50),
    tooth character varying(10),
    surface character varying(20),
    description character varying(500),
    fee numeric(12,2) DEFAULT 0 NOT NULL,
    insurance_estimate numeric(12,2) DEFAULT 0 NOT NULL,
    billing_order character varying(10),
    status character varying(20) DEFAULT 'Planned'::character varying NOT NULL,
    material_id integer,
    notes text,
    is_archived boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    est_patient numeric(12,2),
    duration_minutes integer,
    provider_units integer DEFAULT 1 NOT NULL,
    bill_to character varying(1),
    treatment_plan_item_id character varying(50)
);


--
-- Name: appointment_procedures_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.appointment_procedures_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: appointment_procedures_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.appointment_procedures_id_seq OWNED BY public.appointment_procedures.id;


--
-- Name: appointments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.appointments (
    id character varying(50) NOT NULL,
    patient_id integer,
    provider_id character varying(50) NOT NULL,
    operatory_id character varying(50),
    office_id integer NOT NULL,
    legacy_id character varying(20),
    is_archived boolean DEFAULT false NOT NULL,
    date date NOT NULL,
    start_time time without time zone NOT NULL,
    end_time time without time zone NOT NULL,
    duration integer NOT NULL,
    status character varying(30) DEFAULT 'Scheduled'::character varying NOT NULL,
    is_missed boolean DEFAULT false NOT NULL,
    is_cancelled boolean DEFAULT false NOT NULL,
    is_posted boolean DEFAULT false NOT NULL,
    procedure_label character varying(200),
    is_new_patient boolean DEFAULT false NOT NULL,
    notes text,
    has_lab boolean DEFAULT false NOT NULL,
    lab_cost numeric(10,2),
    lab_sent_on date,
    lab_due_on date,
    lab_received_on date,
    is_blocked boolean DEFAULT false NOT NULL,
    campaign_id character varying(100),
    treatment_plan_id character varying(50),
    confirmed_on timestamp without time zone,
    checked_in_on timestamp without time zone,
    checked_out_on timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    posted_on timestamp without time zone,
    cancellation_note text,
    cancellation_reason character varying(50),
    add_to_call_list boolean DEFAULT false NOT NULL,
    created_by integer,
    updated_by integer,
    lab_dds character varying(100),
    lab_vendor_id integer,
    lab_short_notice boolean DEFAULT false NOT NULL
);


--
-- Name: appointnow_reasons; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.appointnow_reasons (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    reason_code character varying(50) NOT NULL,
    label character varying(200) NOT NULL,
    duration_minutes integer DEFAULT 60 NOT NULL,
    requires_provider boolean DEFAULT false NOT NULL,
    display_order integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    updated_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    requires_payment boolean,
    payment_amount numeric(10,2)
);


--
-- Name: appointnow_reasons_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.appointnow_reasons_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: appointnow_reasons_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.appointnow_reasons_id_seq OWNED BY public.appointnow_reasons.id;


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id bigint NOT NULL,
    tenant_id integer,
    user_id integer,
    action character varying(20) NOT NULL,
    resource_type character varying(100),
    resource_id character varying(100),
    method character varying(10) NOT NULL,
    path character varying(500) NOT NULL,
    status_code integer,
    ip_address character varying(64),
    request_id character varying(64),
    details json,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    patient_id integer,
    office_id integer
);


--
-- Name: audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audit_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_logs_id_seq OWNED BY public.audit_logs.id;


--
-- Name: auth_action_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_action_tokens (
    user_id integer NOT NULL,
    token_hash character varying(64) NOT NULL,
    purpose character varying(30) NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    used_at timestamp without time zone,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: auth_action_tokens_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.auth_action_tokens_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: auth_action_tokens_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.auth_action_tokens_id_seq OWNED BY public.auth_action_tokens.id;


--
-- Name: booking_acknowledgement_texts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.booking_acknowledgement_texts (
    text_hash character varying(64) NOT NULL,
    kind character varying(20) NOT NULL,
    text text NOT NULL,
    version character varying(50),
    first_seen_at timestamp without time zone NOT NULL
);


--
-- Name: booking_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.booking_requests (
    id character varying(40) NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    reason_id character varying(50),
    reason_label character varying(200),
    duration_minutes integer DEFAULT 60 NOT NULL,
    provider_id character varying(50),
    provider_name character varying(255),
    slot_date date NOT NULL,
    start_time time without time zone NOT NULL,
    end_time time without time zone NOT NULL,
    first_name character varying(100),
    last_name character varying(100),
    phone character varying(30),
    email character varying(255),
    date_of_birth date,
    is_new_patient boolean DEFAULT true NOT NULL,
    notes text,
    hold_expires_at timestamp without time zone,
    appointment_id character varying(50),
    patient_id integer,
    decline_reason text,
    actioned_by integer,
    actioned_at timestamp without time zone,
    source_ip character varying(64),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    insurance_info character varying(500),
    disclaimer_accepted boolean DEFAULT false NOT NULL,
    consent_accepted boolean DEFAULT false NOT NULL,
    original_slot_date date,
    original_start_time time without time zone,
    original_end_time time without time zone,
    original_duration_minutes integer,
    original_provider_id character varying(50),
    original_provider_name character varying(255),
    reschedule_count integer DEFAULT 0 NOT NULL,
    rescheduled_by integer,
    rescheduled_at timestamp without time zone,
    contact_notified_at timestamp without time zone,
    contact_notified_via character varying(10),
    payment_terms_accepted boolean,
    acknowledgement_hashes json,
    acknowledgement_version character varying(50),
    acknowledged_at timestamp without time zone,
    status_token_hash character varying(64),
    requires_payment boolean DEFAULT false NOT NULL,
    payment_status character varying(20) DEFAULT 'not_required'::character varying NOT NULL,
    payment_amount numeric(10,2),
    payment_currency character varying(3),
    payment_provider character varying(20),
    payment_link_id character varying(255),
    payment_link_url text,
    payment_link_sent_at timestamp without time zone,
    payment_link_sent_via character varying(10),
    payment_link_expires_at timestamp without time zone,
    payment_note text,
    payment_requested_by integer,
    payment_booking json,
    paid_at timestamp without time zone,
    paid_amount numeric(10,2),
    payment_reference character varying(255),
    payment_method character varying(50),
    ledger_payment_id character varying(50),
    booking_error character varying(500),
    refunded_at timestamp without time zone,
    refund_amount numeric(10,2),
    refund_reference character varying(255),
    refund_reason text,
    refunded_by integer,
    operatory_id character varying(50),
    is_emergency boolean DEFAULT false NOT NULL
);


--
-- Name: campaigns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.campaigns (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer,
    code character varying(100) NOT NULL,
    name character varying(200) NOT NULL,
    description text,
    channel character varying(50),
    start_date date,
    end_date date,
    is_active boolean DEFAULT true NOT NULL,
    created_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: campaigns_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.campaigns_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: campaigns_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.campaigns_id_seq OWNED BY public.campaigns.id;


--
-- Name: caries_risk_assessments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.caries_risk_assessments (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    risk_date date,
    vis_cavities boolean,
    les_not_dentin boolean,
    surf_white_spots boolean,
    rest_in_3yrs boolean,
    cav_rad_dentin boolean,
    prox_enamel_les boolean,
    act_white_spot_surf boolean,
    fir_vis_rest_lst_3yrs boolean,
    foll_up_vis_rest_yr boolean,
    vis_plaque boolean,
    freq_snack boolean,
    pits_and_fissures boolean,
    acidic_ph boolean,
    atp boolean,
    xerostomia boolean,
    cari_read_above_1500 boolean,
    vis_heavy_plaque boolean,
    freq_snack_gt3x boolean,
    deep_pits_fissures boolean,
    recreat_drug boolean,
    saliva_flow_reduced boolean,
    ortho_appliance boolean,
    fluoride_toothpaste boolean,
    fluoride_rinse boolean,
    hx_peridex boolean,
    office_flour_6mon boolean,
    live_work_fw_water boolean,
    f_toothpaste_1x boolean,
    f_toothpaste_2x boolean,
    f_mouth_rinse boolean,
    f_toothpaste_5000ppm boolean,
    f_varnish_6mon boolean,
    office_f_topical_6mon boolean,
    chx_1wk_per_mon boolean,
    xylitol_6mon boolean,
    adeaq_saliva_flow boolean,
    risk_level character varying(20),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100),
    updated_at timestamp without time zone
);


--
-- Name: caries_risk_assessments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.caries_risk_assessments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: caries_risk_assessments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.caries_risk_assessments_id_seq OWNED BY public.caries_risk_assessments.id;


--
-- Name: chart_colors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chart_colors (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    category_type integer,
    name character varying(100) NOT NULL,
    stroke_color character varying(50),
    fill_type character varying(20),
    fill_color character varying(50),
    fill_color2 character varying(50),
    fill_pattern text,
    gradient_angle character varying(20),
    gradient_method character varying(20),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100),
    updated_at timestamp without time zone,
    updated_by integer
);


--
-- Name: chart_colors_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chart_colors_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chart_colors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chart_colors_id_seq OWNED BY public.chart_colors.id;


--
-- Name: chart_conditions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chart_conditions (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    activity_date date,
    tooth character varying(10),
    surface character varying(20),
    region character varying(100),
    area character varying(20),
    description character varying(500),
    condition_code character varying(50),
    procedure_code character varying(20),
    provider_id character varying(50),
    material_id integer,
    chart_as character varying(20),
    is_inactive boolean DEFAULT false NOT NULL,
    notes text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    group_id character varying(64),
    grade character varying(20),
    segment character varying(20),
    root_segment character varying(50),
    tooth_status character varying(30),
    root_scope character varying(10),
    rct_fill character varying(20),
    watch_dir character varying(5),
    watch_x integer,
    watch_y integer,
    status character varying(20),
    updated_at timestamp without time zone,
    updated_by integer
);


--
-- Name: chart_conditions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chart_conditions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chart_conditions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chart_conditions_id_seq OWNED BY public.chart_conditions.id;


--
-- Name: chart_materials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chart_materials (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(100) NOT NULL,
    pattern character varying(100),
    color character varying(50),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    updated_by integer
);


--
-- Name: chart_materials_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chart_materials_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chart_materials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chart_materials_id_seq OWNED BY public.chart_materials.id;


--
-- Name: chart_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chart_settings (
    patient_id integer NOT NULL,
    numbering_system character varying(20) DEFAULT 'UNIVERSAL'::character varying NOT NULL,
    wisdom_visible boolean DEFAULT true NOT NULL,
    occlusal_visible boolean DEFAULT true NOT NULL,
    show_base boolean DEFAULT true NOT NULL,
    show_healthy_pulp boolean DEFAULT false NOT NULL,
    edentulous boolean DEFAULT false NOT NULL,
    arch_mode character varying(10) DEFAULT 'both'::character varying NOT NULL,
    updated_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: chart_status_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chart_status_templates (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(200) NOT NULL,
    label_key character varying(100),
    template_type character varying(50) NOT NULL,
    arch character varying(10),
    material character varying(50),
    teeth json,
    implants json,
    missing json,
    is_active boolean DEFAULT true NOT NULL,
    created_by integer,
    updated_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: chart_status_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chart_status_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chart_status_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chart_status_templates_id_seq OWNED BY public.chart_status_templates.id;


--
-- Name: chart_tooth_notes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chart_tooth_notes (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    tooth character varying(10) NOT NULL,
    note text,
    updated_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: chart_tooth_notes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chart_tooth_notes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chart_tooth_notes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chart_tooth_notes_id_seq OWNED BY public.chart_tooth_notes.id;


--
-- Name: claim_attachments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.claim_attachments (
    tenant_id integer NOT NULL,
    claim_id character varying(50) NOT NULL,
    attachment_type character varying(50),
    file_name character varying(500) NOT NULL,
    content_type character varying(100),
    file_size bigint,
    file_path character varying(500) NOT NULL,
    file_url character varying(500) NOT NULL,
    is_deleted boolean NOT NULL,
    created_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: claim_attachments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.claim_attachments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: claim_attachments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.claim_attachments_id_seq OWNED BY public.claim_attachments.id;


--
-- Name: claim_submissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.claim_submissions (
    id integer NOT NULL,
    claim_id character varying(50) NOT NULL,
    legacy_id character varying(20),
    batch_id character varying(50),
    is_preauth boolean DEFAULT false NOT NULL,
    total_charges numeric(12,2),
    num_lines integer,
    submission_status character varying(10),
    claim_text text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer
);


--
-- Name: claim_submissions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.claim_submissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: claim_submissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.claim_submissions_id_seq OWNED BY public.claim_submissions.id;


--
-- Name: code_bundle_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.code_bundle_items (
    id integer NOT NULL,
    bundle_id integer NOT NULL,
    legacy_id character varying(20),
    procedure_code character varying(20) NOT NULL,
    tooth character varying(10),
    sort_order integer DEFAULT 1 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    surface character varying(20),
    quadrant character varying(10)
);


--
-- Name: code_bundle_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.code_bundle_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: code_bundle_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.code_bundle_items_id_seq OWNED BY public.code_bundle_items.id;


--
-- Name: code_bundles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.code_bundles (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(100) NOT NULL,
    display_code character varying(50),
    description character varying(255),
    same_tooth boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer
);


--
-- Name: code_bundles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.code_bundles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: code_bundles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.code_bundles_id_seq OWNED BY public.code_bundles.id;


--
-- Name: codes_view; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.codes_view (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    code character varying(20) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100)
);


--
-- Name: codes_view_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.codes_view_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: codes_view_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.codes_view_id_seq OWNED BY public.codes_view.id;


--
-- Name: collection_agencies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collection_agencies (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(255) NOT NULL,
    address character varying(255),
    address2 character varying(255),
    city character varying(100),
    state character varying(50),
    zip character varying(20),
    phone character varying(20),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100)
);


--
-- Name: collection_agencies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.collection_agencies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: collection_agencies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.collection_agencies_id_seq OWNED BY public.collection_agencies.id;


--
-- Name: consent_signatures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.consent_signatures (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    consent_id integer NOT NULL,
    role character varying(30) NOT NULL,
    signer_user_id integer,
    signer_provider_id character varying(50),
    signer_name character varying(120),
    signature_data text,
    signature_len integer,
    device_source character varying(20),
    signed_at timestamp without time zone,
    captured_at timestamp without time zone,
    sig_string text,
    sig_format character varying(24),
    sig_compression smallint,
    sig_encryption smallint,
    point_count integer,
    stroke_count integer,
    device_vendor character varying(20),
    device_model character varying(40),
    device_serial character varying(40),
    captured_user_agent character varying(255),
    content_hash character varying(64),
    is_active boolean DEFAULT true NOT NULL,
    voided_at timestamp without time zone,
    voided_by integer,
    created_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: consent_signatures_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.consent_signatures_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: consent_signatures_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.consent_signatures_id_seq OWNED BY public.consent_signatures.id;


--
-- Name: conversation_participants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversation_participants (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    conversation_id uuid NOT NULL,
    user_id integer NOT NULL,
    role character varying(20),
    is_pinned boolean,
    is_muted boolean,
    is_archived boolean,
    is_blocked boolean,
    last_read_message_id uuid,
    last_read_at timestamp without time zone,
    unread_count integer,
    joined_at timestamp without time zone DEFAULT now() NOT NULL,
    left_at timestamp without time zone
);


--
-- Name: conversation_participants_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.conversation_participants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: conversation_participants_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.conversation_participants_id_seq OWNED BY public.conversation_participants.id;


--
-- Name: conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversations (
    id uuid NOT NULL,
    tenant_id integer NOT NULL,
    type character varying(20),
    title character varying(255),
    dedupe_key character varying(100),
    created_by integer NOT NULL,
    last_message_id uuid,
    last_message_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: definition_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.definition_groups (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(50),
    group_code character varying(50) NOT NULL,
    description character varying(255) NOT NULL,
    key1_label character varying(100),
    key2_label character varying(100),
    is_editable boolean DEFAULT true NOT NULL,
    can_add boolean DEFAULT true NOT NULL,
    group_type character varying(20),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    updated_by integer
);


--
-- Name: definition_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.definition_groups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: definition_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.definition_groups_id_seq OWNED BY public.definition_groups.id;


--
-- Name: definitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.definitions (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    group_code character varying(50) NOT NULL,
    key1 character varying(50) NOT NULL,
    key2 character varying(50),
    description character varying(255) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    is_flash_alert boolean DEFAULT false NOT NULL,
    blocks_charges boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    color character varying(20),
    sort_order integer,
    input_type character varying(20),
    updated_at timestamp without time zone,
    updated_by integer,
    section character varying(100)
);


--
-- Name: definitions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.definitions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: definitions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.definitions_id_seq OWNED BY public.definitions.id;


--
-- Name: dicom_instances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dicom_instances (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    series_id integer NOT NULL,
    sop_instance_uid character varying(64) NOT NULL,
    sop_class_uid character varying(64),
    instance_number character varying(32),
    rows integer,
    columns integer,
    bits_allocated integer,
    photometric_interpretation character varying(32),
    window_center character varying(64),
    window_width character varying(64),
    applied_window_center character varying(64),
    applied_window_width character varying(64),
    anatomic_codes json,
    tooth_numbers json,
    original_object_id integer,
    web_object_id integer,
    thumb_object_id integer,
    derivative_status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    derivative_error text,
    superseded_by integer,
    has_original_attributes boolean DEFAULT false NOT NULL,
    original_attributes json,
    is_deleted boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: dicom_instances_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dicom_instances_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dicom_instances_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dicom_instances_id_seq OWNED BY public.dicom_instances.id;


--
-- Name: dicom_series; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dicom_series (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    study_id integer NOT NULL,
    series_instance_uid character varying(64) NOT NULL,
    modality character varying(16),
    series_number character varying(32),
    body_part character varying(64),
    description character varying(255),
    is_deleted boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: dicom_series_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dicom_series_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dicom_series_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dicom_series_id_seq OWNED BY public.dicom_series.id;


--
-- Name: dicom_studies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dicom_studies (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    patient_id integer,
    study_instance_uid character varying(64) NOT NULL,
    accession_number character varying(64),
    study_id character varying(64),
    study_date date,
    study_time character varying(24),
    description character varying(255),
    modalities json,
    source_patient_id_raw character varying(64),
    identity_review_required boolean DEFAULT false NOT NULL,
    is_deleted boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: dicom_studies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dicom_studies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dicom_studies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dicom_studies_id_seq OWNED BY public.dicom_studies.id;


--
-- Name: eligibility_checks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.eligibility_checks (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer,
    subscriber_id integer NOT NULL,
    ins_plan_id integer,
    carrier_id integer,
    patient_id integer,
    requested_by integer,
    status character varying(20) NOT NULL,
    http_status_code integer,
    error_message character varying(300),
    request_payload json,
    response_payload json,
    coverage_status character varying(20),
    copay_amount numeric(10,2),
    deductible_remaining numeric(10,2),
    plan_max_remaining numeric(10,2),
    checked_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: eligibility_checks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.eligibility_checks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: eligibility_checks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.eligibility_checks_id_seq OWNED BY public.eligibility_checks.id;


--
-- Name: email_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.email_messages (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer,
    patient_id integer,
    appointment_id character varying(50),
    to_email character varying(255) NOT NULL,
    from_email character varying(255),
    subject character varying(500) NOT NULL,
    body_html text,
    body_text text,
    provider character varying(20),
    provider_message_id character varying(120),
    send_status character varying(30) DEFAULT 'queued'::character varying NOT NULL,
    sent_at timestamp without time zone,
    delivered_at timestamp without time zone,
    opened_at timestamp without time zone,
    error_message text,
    message_type character varying(50),
    client_id character varying(40),
    is_read boolean DEFAULT false NOT NULL,
    status_payload_hash character varying(64),
    created_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: email_messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.email_messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: email_messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.email_messages_id_seq OWNED BY public.email_messages.id;


--
-- Name: employers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.employers (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(255) NOT NULL,
    address character varying(255),
    city character varying(100),
    state character varying(50),
    zip character varying(20),
    phone character varying(20),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    salesrep character varying(255),
    contact_person character varying(255),
    updated_at timestamp without time zone,
    created_by integer,
    updated_by integer,
    address2 character varying(255)
);


--
-- Name: employers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.employers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: employers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.employers_id_seq OWNED BY public.employers.id;


--
-- Name: explosion_code_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.explosion_code_items (
    id integer NOT NULL,
    explosion_code_id integer NOT NULL,
    procedure_code character varying(20) NOT NULL,
    display_order integer DEFAULT 0 NOT NULL,
    default_fee numeric(12,2),
    tooth character varying(10),
    surface character varying(20),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    quadrant character varying(10)
);


--
-- Name: explosion_code_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.explosion_code_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: explosion_code_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.explosion_code_items_id_seq OWNED BY public.explosion_code_items.id;


--
-- Name: explosion_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.explosion_codes (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer,
    code character varying(50) NOT NULL,
    description character varying(255),
    is_active boolean DEFAULT true NOT NULL,
    created_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: explosion_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.explosion_codes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: explosion_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.explosion_codes_id_seq OWNED BY public.explosion_codes.id;


--
-- Name: fee_schedule_assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fee_schedule_assignments (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    ins_plan_id integer,
    carrier_id integer,
    provider_id character varying(50),
    office_id integer,
    fee_schedule_id integer NOT NULL,
    specialty_id character varying(20),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100),
    office_group_id integer,
    updated_at timestamp without time zone,
    updated_by integer
);


--
-- Name: fee_schedule_assignments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.fee_schedule_assignments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: fee_schedule_assignments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.fee_schedule_assignments_id_seq OWNED BY public.fee_schedule_assignments.id;


--
-- Name: fee_schedule_entries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fee_schedule_entries (
    id integer NOT NULL,
    fee_schedule_id integer NOT NULL,
    procedure_code character varying(20) NOT NULL,
    patient_fee numeric(10,2),
    insurance_fee numeric(10,2),
    effective_date date DEFAULT CURRENT_DATE NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    amb_code character varying(20),
    tenant_id integer,
    is_no_charge boolean DEFAULT false NOT NULL,
    updated_at timestamp without time zone,
    created_by integer,
    updated_by integer
);


--
-- Name: fee_schedule_entries_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.fee_schedule_entries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: fee_schedule_entries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.fee_schedule_entries_id_seq OWNED BY public.fee_schedule_entries.id;


--
-- Name: fee_schedules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fee_schedules (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(255) NOT NULL,
    fee_type character varying(50),
    ins_plan_id integer,
    office_id integer,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    effective_date date,
    version integer DEFAULT 1,
    parent_schedule_id integer,
    pricing_model character varying(12) DEFAULT 'percentage'::character varying NOT NULL,
    CONSTRAINT ck_fee_schedules_fee_type CHECK (((fee_type)::text = ANY ((ARRAY['ucr'::character varying, 'standard'::character varying, 'plan'::character varying, 'carrier'::character varying])::text[]))),
    CONSTRAINT ck_fee_schedules_pricing_model CHECK (((pricing_model)::text = ANY ((ARRAY['percentage'::character varying, 'copay'::character varying])::text[]))),
    CONSTRAINT ck_fee_schedules_pricing_model_needs_payer CHECK ((((pricing_model)::text = 'percentage'::text) OR ((fee_type)::text = ANY ((ARRAY['plan'::character varying, 'carrier'::character varying])::text[]))))
);


--
-- Name: fee_schedules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.fee_schedules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: fee_schedules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.fee_schedules_id_seq OWNED BY public.fee_schedules.id;


--
-- Name: icd_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.icd_codes (
    code character varying(20) NOT NULL,
    description character varying(500) NOT NULL,
    icd9 character varying(20),
    icd10 character varying(20),
    snomed character varying(30),
    is_active boolean NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: icd_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.icd_codes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: icd_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.icd_codes_id_seq OWNED BY public.icd_codes.id;


--
-- Name: image_details; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.image_details (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer,
    image_group_id integer,
    legacy_id character varying(20),
    tile_id character varying(20),
    filename character varying(500),
    notes text,
    teeth character varying(100),
    file_size bigint,
    is_deleted boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: image_details_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.image_details_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: image_details_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.image_details_id_seq OWNED BY public.image_details.id;


--
-- Name: image_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.image_groups (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer,
    patient_id integer,
    template_id integer,
    legacy_id character varying(20),
    name character varying(255),
    group_type character varying(20),
    ext_id character varying(50),
    source character varying(50),
    source2 character varying(50),
    is_deleted boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100),
    updated_at timestamp without time zone
);


--
-- Name: image_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.image_groups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: image_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.image_groups_id_seq OWNED BY public.image_groups.id;


--
-- Name: imaging_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.imaging_templates (
    id integer NOT NULL,
    office_id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(255) NOT NULL,
    template_type character varying(20),
    dentition character varying(5),
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: imaging_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.imaging_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: imaging_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.imaging_templates_id_seq OWNED BY public.imaging_templates.id;


--
-- Name: ins_custom_coverage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ins_custom_coverage (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    start_code character varying(20) NOT NULL,
    end_code character varying(20) NOT NULL,
    description character varying(255),
    coverage_pct numeric(5,2),
    ded_waived boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100)
);


--
-- Name: ins_custom_coverage_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ins_custom_coverage_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ins_custom_coverage_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ins_custom_coverage_id_seq OWNED BY public.ins_custom_coverage.id;


--
-- Name: insurance_carriers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.insurance_carriers (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(255) NOT NULL,
    payer_id character varying(50),
    phone character varying(20),
    phone2 character varying(20),
    address character varying(255),
    city character varying(100),
    state character varying(50),
    zip character varying(20),
    website character varying(255),
    notes text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    carrier_type character varying(20),
    national_id character varying(50),
    claim_type character varying(10),
    fee_id character varying(20),
    address2 character varying(255),
    contact character varying(255),
    ref_num character varying(50),
    vbs_id character varying(50),
    vbs_pgid character varying(50),
    cda_carrier_transaction_counter character varying(50),
    created_on timestamp without time zone,
    created_by character varying(100),
    modified_on timestamp without time zone,
    modified_by character varying(100),
    fax character varying(20),
    email character varying(255),
    supports_realtime_eligibility boolean,
    supports_claim_status boolean,
    supports_dxc_attachment boolean,
    insurance_type character varying(50),
    updated_at timestamp without time zone,
    updated_by integer,
    stedi_payer_verified boolean,
    stedi_payer_verified_at timestamp without time zone
);


--
-- Name: insurance_carriers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.insurance_carriers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: insurance_carriers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.insurance_carriers_id_seq OWNED BY public.insurance_carriers.id;


--
-- Name: insurance_claims; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.insurance_claims (
    id character varying(50) NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    claim_number character varying(50) NOT NULL,
    status character varying(30) DEFAULT 'draft'::character varying NOT NULL,
    claim_type character varying(20) DEFAULT 'primary'::character varying NOT NULL,
    billing_order character varying(10),
    date_of_service_from date,
    date_of_service_to date,
    total_billed numeric(12,2) DEFAULT 0 NOT NULL,
    total_paid numeric(12,2) DEFAULT 0 NOT NULL,
    est_insurance numeric(12,2) DEFAULT 0 NOT NULL,
    submitted_date date,
    paid_date date,
    close_date date,
    billing_provider_id character varying(50),
    treating_provider_id character varying(50),
    carrier_id integer,
    ins_plan_id integer,
    is_preauth boolean DEFAULT false NOT NULL,
    notes text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer,
    write_off_amount numeric(12,2),
    write_off_mode character varying(10),
    write_off_value numeric(12,2),
    opening_paid numeric(12,2),
    is_epsdt boolean DEFAULT false NOT NULL,
    is_locum_tenens boolean DEFAULT false NOT NULL,
    date_last_srp date,
    icd_qualifier character varying(2),
    icd_1 character varying(10),
    icd_2 character varying(10),
    icd_3 character varying(10),
    icd_4 character varying(10),
    other_fees numeric(10,2),
    missing_teeth character varying(120),
    other_ins_plan_id integer,
    has_other_coverage boolean,
    predetermination_number character varying(50),
    remarks text,
    signature_on_file boolean DEFAULT false NOT NULL,
    place_of_treatment character varying(2),
    is_ortho boolean DEFAULT false NOT NULL,
    ortho_appliance_date date,
    ortho_months_remaining integer,
    prosthesis_replacement boolean DEFAULT false NOT NULL,
    prosthesis_prior_date date,
    accident_type character varying(15),
    accident_date date,
    accident_state character varying(2)
);


--
-- Name: insurance_coverage_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.insurance_coverage_rules (
    id integer NOT NULL,
    ins_plan_id integer NOT NULL,
    legacy_id character varying(20),
    start_code character varying(20) NOT NULL,
    end_code character varying(20) NOT NULL,
    category character varying(100),
    description character varying(255),
    coverage_pct numeric(5,2),
    ded_waived boolean DEFAULT false NOT NULL,
    freq_limit integer,
    age_limit character varying(50),
    wait_period character varying(50),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    created_by integer,
    updated_by integer,
    age_min integer,
    age_max integer,
    wait_months integer
);


--
-- Name: insurance_coverage_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.insurance_coverage_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: insurance_coverage_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.insurance_coverage_rules_id_seq OWNED BY public.insurance_coverage_rules.id;


--
-- Name: insurance_plan_frequency_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.insurance_plan_frequency_groups (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    ins_plan_id integer NOT NULL,
    code_group character varying(20) NOT NULL,
    description character varying(255),
    freq_limit integer,
    whole_mouth boolean DEFAULT false NOT NULL,
    per_day_quantity integer,
    created_by integer,
    updated_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: insurance_plan_frequency_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.insurance_plan_frequency_groups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: insurance_plan_frequency_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.insurance_plan_frequency_groups_id_seq OWNED BY public.insurance_plan_frequency_groups.id;


--
-- Name: insurance_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.insurance_plans (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    carrier_id integer NOT NULL,
    employer_id integer,
    legacy_id character varying(20),
    group_number character varying(100),
    plan_type character varying(50),
    is_prepaid boolean DEFAULT false NOT NULL,
    individual_max numeric(10,2),
    individual_deductible numeric(10,2),
    ortho_max numeric(10,2),
    family_max numeric(10,2),
    family_deductible numeric(10,2),
    anniversary_date date,
    coverage_type character varying(10),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    anniversary_expiry_date date,
    updated_at timestamp without time zone,
    created_on timestamp without time zone,
    created_by character varying(100),
    modified_on timestamp without time zone,
    modified_by character varying(100),
    updated_by integer,
    anniversary_month integer,
    anniversary_day integer,
    fees_to_print character varying(20),
    claim_option character varying(20),
    form_to_print character varying(20),
    reporting_subtype character varying(50),
    network_type character varying(20),
    noa_only boolean DEFAULT false NOT NULL,
    per_visit_copay numeric(10,2),
    lifetime_ortho_benefits boolean DEFAULT false NOT NULL,
    plan_notes text,
    is_locked boolean DEFAULT false NOT NULL,
    locked_at timestamp without time zone,
    locked_by integer,
    is_non_dup_benefits boolean DEFAULT false NOT NULL,
    legacy_prepaid_code character varying(5)
);


--
-- Name: insurance_plans_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.insurance_plans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: insurance_plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.insurance_plans_id_seq OWNED BY public.insurance_plans.id;


--
-- Name: insurance_subscribers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.insurance_subscribers (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    ins_plan_id integer NOT NULL,
    subscriber_patient_id integer,
    office_id integer,
    sub_first_name character varying(100),
    sub_last_name character varying(100),
    sub_mi character varying(10),
    sub_address character varying(255),
    sub_city character varying(100),
    sub_state character varying(50),
    sub_zip character varying(20),
    sub_dob date,
    sub_gender character varying(10),
    sub_ssn character varying(20),
    sub_member_id character varying(100),
    group_number character varying(100),
    effective_date date,
    term_date date,
    family_max_remaining numeric(10,2),
    family_ded_remaining numeric(10,2),
    ortho_remaining numeric(10,2),
    anniversary_date date,
    elig_status character varying(20),
    elig_verified_on timestamp without time zone,
    elig_verified_by character varying(100),
    elig_notes text,
    notes text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    sub_address2 character varying(255),
    marital_status character varying(20),
    sub_phone character varying(20),
    plan_effective_date date,
    plan_term_date date,
    elig_method character varying(20),
    sub_suffix character varying(10)
);


--
-- Name: insurance_subscribers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.insurance_subscribers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: insurance_subscribers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.insurance_subscribers_id_seq OWNED BY public.insurance_subscribers.id;


--
-- Name: labs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.labs (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer,
    name character varying(200) NOT NULL,
    code character varying(50),
    contact_name character varying(200),
    phone character varying(50),
    fax character varying(50),
    email character varying(255),
    address_line1 character varying(255),
    address_line2 character varying(255),
    city character varying(100),
    state character varying(50),
    zip character varying(20),
    default_turnaround_days integer,
    notes text,
    is_active boolean DEFAULT true NOT NULL,
    created_by integer,
    updated_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now()
);


--
-- Name: labs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.labs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: labs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.labs_id_seq OWNED BY public.labs.id;


--
-- Name: ledger_insurance_details; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ledger_insurance_details (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    procedure_id character varying(50),
    legacy_ledger_id character varying(20),
    claim_id character varying(50),
    office_id integer,
    prim_estimated numeric(12,2),
    prim_ind_max numeric(12,2),
    prim_deductible numeric(12,2),
    prim_ins_paid numeric(12,2),
    prim_ins_adjust numeric(12,2),
    sec_estimated numeric(12,2),
    sec_ins_paid numeric(12,2),
    sec_ins_adjust numeric(12,2),
    ter_ins_paid numeric(12,2),
    prim_ins_plan_id integer,
    sec_ins_plan_id integer,
    ter_ins_plan_id integer,
    prim_posted boolean DEFAULT false NOT NULL,
    sec_posted boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    payment_date date,
    payment_method character varying(50),
    check_number character varying(100),
    bank_number character varying(100),
    eob_number character varying(100),
    eft_trace_number character varying(100),
    created_by integer,
    sec_deductible numeric(12,2),
    ter_estimated numeric(12,2),
    ter_deductible numeric(12,2),
    ter_ins_adjust numeric(12,2),
    ter_posted boolean DEFAULT false NOT NULL,
    notes text,
    is_void boolean DEFAULT false NOT NULL,
    void_reason text,
    voided_at timestamp without time zone,
    voided_by integer
);


--
-- Name: ledger_insurance_details_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ledger_insurance_details_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ledger_insurance_details_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ledger_insurance_details_id_seq OWNED BY public.ledger_insurance_details.id;


--
-- Name: letter_batch_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.letter_batch_items (
    id integer NOT NULL,
    batch_id integer NOT NULL,
    patient_id integer NOT NULL,
    status character varying(20) DEFAULT 'rendered'::character varying NOT NULL,
    unresolved_tokens json,
    rendered_html text,
    document_id integer,
    error text,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: letter_batch_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.letter_batch_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: letter_batch_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.letter_batch_items_id_seq OWNED BY public.letter_batch_items.id;


--
-- Name: letter_batch_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.letter_batch_runs (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer,
    template_id integer NOT NULL,
    status character varying(20) DEFAULT 'queued'::character varying NOT NULL,
    requested integer DEFAULT 0 NOT NULL,
    processed integer DEFAULT 0 NOT NULL,
    succeeded integer DEFAULT 0 NOT NULL,
    failed integer DEFAULT 0 NOT NULL,
    options json,
    error text,
    finished_at timestamp without time zone,
    created_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: letter_batch_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.letter_batch_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: letter_batch_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.letter_batch_runs_id_seq OWNED BY public.letter_batch_runs.id;


--
-- Name: letter_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.letter_templates (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(255) NOT NULL,
    letter_type character varying(10),
    channel character varying(20),
    title character varying(255),
    body_html text,
    is_editable boolean DEFAULT true NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: letter_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.letter_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: letter_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.letter_templates_id_seq OWNED BY public.letter_templates.id;


--
-- Name: medical_history_details; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.medical_history_details (
    id integer NOT NULL,
    history_id integer NOT NULL,
    legacy_id character varying(20),
    question_code character varying(100) NOT NULL,
    question_text text,
    answer_code character varying(20),
    answer_text text,
    notes text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    answer_type character varying(20),
    section character varying(100)
);


--
-- Name: medical_history_details_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.medical_history_details_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: medical_history_details_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.medical_history_details_id_seq OWNED BY public.medical_history_details.id;


--
-- Name: medical_history_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.medical_history_records (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    legacy_id character varying(20),
    signature_id integer,
    is_archived boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer,
    tenant_id integer,
    scope character varying(20),
    content_hash character varying(64),
    item_count integer,
    comments text,
    completed_at timestamp without time zone,
    completed_by integer,
    source_patient_id integer,
    copied_at timestamp without time zone,
    updated_at timestamp without time zone,
    updated_by integer
);


--
-- Name: medical_history_records_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.medical_history_records_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: medical_history_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.medical_history_records_id_seq OWNED BY public.medical_history_records.id;


--
-- Name: message_attachments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.message_attachments (
    id uuid NOT NULL,
    tenant_id integer NOT NULL,
    message_id uuid,
    uploader_id integer NOT NULL,
    kind character varying(20) NOT NULL,
    name character varying(255) NOT NULL,
    mime_type character varying(150) NOT NULL,
    size_bytes bigint NOT NULL,
    storage_key character varying(500) NOT NULL,
    width integer,
    height integer,
    status character varying(20),
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: message_reactions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.message_reactions (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    message_id uuid NOT NULL,
    user_id integer NOT NULL,
    emoji character varying(32) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: message_reactions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.message_reactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: message_reactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.message_reactions_id_seq OWNED BY public.message_reactions.id;


--
-- Name: message_receipts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.message_receipts (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    message_id uuid NOT NULL,
    user_id integer NOT NULL,
    delivered_at timestamp without time zone,
    read_at timestamp without time zone
);


--
-- Name: message_receipts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.message_receipts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: message_receipts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.message_receipts_id_seq OWNED BY public.message_receipts.id;


--
-- Name: message_recipient_states; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.message_recipient_states (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    message_id uuid NOT NULL,
    user_id integer NOT NULL,
    is_deleted boolean,
    deleted_at timestamp without time zone
);


--
-- Name: message_recipient_states_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.message_recipient_states_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: message_recipient_states_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.message_recipient_states_id_seq OWNED BY public.message_recipient_states.id;


--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    id uuid NOT NULL,
    tenant_id integer NOT NULL,
    conversation_id uuid NOT NULL,
    sender_id integer NOT NULL,
    body text,
    reply_to_id uuid,
    forwarded_from character varying(255),
    client_id character varying(64),
    is_edited boolean,
    edited_at timestamp without time zone,
    deleted_for_everyone boolean,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: mig_dicom_manifest; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mig_dicom_manifest (
    id bigint NOT NULL,
    source_path text NOT NULL,
    source_size_bytes bigint,
    content_sha256 character(64),
    gcs_object_key text,
    upload_status text,
    sop_instance_uid character varying(64),
    sop_class_uid character varying(64),
    study_instance_uid character varying(64),
    series_instance_uid character varying(64),
    accession_number character varying(64),
    study_id character varying(64),
    series_number character varying(32),
    instance_number character varying(32),
    transfer_syntax_uid character varying(64),
    patient_id character varying(64),
    patient_name_raw text,
    patient_birth_date character varying(16),
    patient_sex character varying(8),
    modality character varying(16),
    study_date character varying(16),
    study_time character varying(24),
    content_date character varying(16),
    body_part_examined character varying(64),
    view_position character varying(32),
    image_comments text,
    anatomic_structure_codes jsonb,
    rows integer,
    columns integer,
    bits_allocated integer,
    photometric_interpretation character varying(32),
    window_center character varying(64),
    window_width character varying(64),
    manufacturer character varying(128),
    manufacturer_model_name character varying(128),
    software_versions character varying(128),
    institution_name character varying(128),
    source_ae_title character varying(64),
    has_original_attributes boolean DEFAULT false,
    loaded_at timestamp with time zone DEFAULT now()
);


--
-- Name: mig_dicom_manifest_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.mig_dicom_manifest_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: mig_dicom_manifest_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.mig_dicom_manifest_id_seq OWNED BY public.mig_dicom_manifest.id;


--
-- Name: mig_dicom_object; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mig_dicom_object (
    content_sha256 character(64) NOT NULL,
    size_bytes bigint,
    gcs_object_key text,
    source_copies integer DEFAULT 1
);


--
-- Name: mig_patient_link; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mig_patient_link (
    patient_id_raw character varying(64) NOT NULL,
    patient_id integer,
    tenant_id integer,
    match_method character varying(32) NOT NULL,
    confidence real,
    image_count integer,
    resolved_at timestamp with time zone DEFAULT now()
);


--
-- Name: note_macros; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.note_macros (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(100) NOT NULL,
    content text NOT NULL,
    category character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer,
    updated_at timestamp without time zone,
    updated_by integer
);


--
-- Name: note_macros_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.note_macros_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: note_macros_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.note_macros_id_seq OWNED BY public.note_macros.id;


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    user_id integer NOT NULL,
    category character varying(50),
    title character varying(255) NOT NULL,
    body text,
    ref_type character varying(50),
    ref_id character varying(50),
    is_read boolean DEFAULT false NOT NULL,
    read_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.notifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notifications_id_seq OWNED BY public.notifications.id;


--
-- Name: office_advanced_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.office_advanced_settings (
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    finance_charge_pct numeric(5,2),
    min_balance numeric(12,2),
    min_charge numeric(12,2),
    days_before_charge integer,
    sales_tax_pct numeric(5,2),
    default_appt_duration integer,
    scheduler_end_date date,
    place_of_service character varying(50),
    area_code character varying(10),
    default_city character varying(100),
    default_state character varying(50),
    default_zip character varying(20),
    preferred_provider_id character varying(50),
    is_ortho boolean NOT NULL,
    hipaa_notice text,
    consent_forms text,
    send_ecard boolean NOT NULL,
    effective_date date,
    updated_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: office_advanced_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.office_advanced_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: office_advanced_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.office_advanced_settings_id_seq OWNED BY public.office_advanced_settings.id;


--
-- Name: office_code_bundles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.office_code_bundles (
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    bundle_id integer NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: office_code_bundles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.office_code_bundles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: office_code_bundles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.office_code_bundles_id_seq OWNED BY public.office_code_bundles.id;


--
-- Name: office_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.office_groups (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(255) NOT NULL,
    address character varying(255),
    address2 character varying(255),
    city character varying(100),
    state character varying(50),
    zip character varying(20),
    phone character varying(20),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100)
);


--
-- Name: office_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.office_groups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: office_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.office_groups_id_seq OWNED BY public.office_groups.id;


--
-- Name: office_integrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.office_integrations (
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    service_email character varying(255),
    service_email_verified boolean NOT NULL,
    ai_assist_enabled boolean NOT NULL,
    patient_comm_url character varying(500),
    patient_portal_url character varying(500),
    dentiray_storage_format character varying(50),
    transfirst_device character varying(100),
    dosespot_clinic_id character varying(100),
    dosespot_key_enc text,
    accepted_cards character varying(255),
    updated_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    service_email_verified_at timestamp without time zone,
    service_email_verification_hash character varying(64),
    service_email_verification_sent_at timestamp without time zone,
    service_email_verification_expires_at timestamp without time zone,
    service_email_verification_attempts integer DEFAULT 0 NOT NULL
);


--
-- Name: office_integrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.office_integrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: office_integrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.office_integrations_id_seq OWNED BY public.office_integrations.id;


--
-- Name: office_letter_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.office_letter_templates (
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    letter_template_id integer NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: office_letter_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.office_letter_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: office_letter_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.office_letter_templates_id_seq OWNED BY public.office_letter_templates.id;


--
-- Name: office_note_macros; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.office_note_macros (
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    note_macro_id integer NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: office_note_macros_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.office_note_macros_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: office_note_macros_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.office_note_macros_id_seq OWNED BY public.office_note_macros.id;


--
-- Name: office_phone_assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.office_phone_assignments (
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    assignment_type character varying(30) NOT NULL,
    phone_number character varying(20),
    is_model_office boolean NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    messaging_service_sid character varying(40)
);


--
-- Name: office_phone_assignments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.office_phone_assignments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: office_phone_assignments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.office_phone_assignments_id_seq OWNED BY public.office_phone_assignments.id;


--
-- Name: office_prescription_library; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.office_prescription_library (
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    prescription_library_id integer NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: office_prescription_library_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.office_prescription_library_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: office_prescription_library_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.office_prescription_library_id_seq OWNED BY public.office_prescription_library.id;


--
-- Name: office_procedure_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.office_procedure_codes (
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    procedure_code character varying(20) NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: office_procedure_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.office_procedure_codes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: office_procedure_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.office_procedure_codes_id_seq OWNED BY public.office_procedure_codes.id;


--
-- Name: office_production_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.office_production_types (
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    production_type_id integer NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: office_production_types_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.office_production_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: office_production_types_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.office_production_types_id_seq OWNED BY public.office_production_types.id;


--
-- Name: office_schedule_days; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.office_schedule_days (
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    day_of_week integer NOT NULL,
    is_closed boolean NOT NULL,
    start_time time without time zone,
    end_time time without time zone,
    lunch_start time without time zone,
    lunch_end time without time zone,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: office_schedule_days_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.office_schedule_days_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: office_schedule_days_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.office_schedule_days_id_seq OWNED BY public.office_schedule_days.id;


--
-- Name: office_smart_assist; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.office_smart_assist (
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    enabled boolean NOT NULL,
    updated_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: office_smart_assist_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.office_smart_assist_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: office_smart_assist_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.office_smart_assist_id_seq OWNED BY public.office_smart_assist.id;


--
-- Name: office_smart_assist_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.office_smart_assist_items (
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    item_code character varying(50) NOT NULL,
    description character varying(500),
    frequency character varying(30),
    sms_template_id character varying(50),
    include_unpaid_balance boolean NOT NULL,
    is_enabled boolean NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: office_smart_assist_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.office_smart_assist_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: office_smart_assist_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.office_smart_assist_items_id_seq OWNED BY public.office_smart_assist_items.id;


--
-- Name: office_statement_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.office_statement_settings (
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    message_general character varying(100),
    message_current character varying(100),
    message_30 character varying(100),
    message_60 character varying(100),
    message_90 character varying(100),
    message_120 character varying(100),
    correspondence_name character varying(255),
    logo_option character varying(20) NOT NULL,
    logo_url character varying(500),
    address_source character varying(20) NOT NULL,
    statement_address_1 character varying(255),
    statement_address_2 character varying(255),
    statement_city character varying(100),
    statement_state character varying(50),
    statement_zip character varying(20),
    statement_phone character varying(20),
    updated_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: office_statement_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.office_statement_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: office_statement_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.office_statement_settings_id_seq OWNED BY public.office_statement_settings.id;


--
-- Name: offices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.offices (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    office_code character varying(20) NOT NULL,
    name character varying(255) NOT NULL,
    short_id character varying(20),
    address_line1 character varying(255),
    address_line2 character varying(255),
    city character varying(100),
    state character varying(50),
    zip character varying(20),
    phone character varying(20),
    fax character varying(20),
    email character varying(255),
    timezone character varying(50) DEFAULT 'America/New_York'::character varying NOT NULL,
    slot_interval_minutes integer DEFAULT 10 NOT NULL,
    schedule_start_hour integer DEFAULT 8 NOT NULL,
    schedule_end_hour integer DEFAULT 17 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    created_by integer,
    phone_2 character varying(20),
    phone_ext character varying(10),
    tax_id character varying(50),
    billing_provider_id character varying(50),
    use_billing_license boolean DEFAULT false,
    office_group_id integer,
    opening_date date,
    default_fee_schedule_id integer,
    default_ucr_fee_schedule_id integer,
    corporate_name character varying(255),
    npi character varying(10),
    taxonomy_code character varying(10),
    treatment_address_line1 character varying(255),
    treatment_address_line2 character varying(255),
    treatment_city character varying(100),
    treatment_state character varying(50),
    treatment_zip character varying(20),
    unpriced_charge_policy character varying(10) DEFAULT 'flag'::character varying NOT NULL,
    appointnow_requires_payment boolean DEFAULT false NOT NULL,
    appointnow_payment_amount numeric(10,2),
    CONSTRAINT ck_offices_unpriced_charge_policy CHECK (((unpriced_charge_policy)::text = ANY ((ARRAY['flag'::character varying, 'refuse'::character varying])::text[])))
);


--
-- Name: offices_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.offices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: offices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.offices_id_seq OWNED BY public.offices.id;


--
-- Name: operatories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.operatories (
    id character varying(50) NOT NULL,
    office_id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(100) NOT NULL,
    display_order integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    provider_id character varying(50)
);


--
-- Name: ortho_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ortho_plans (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    procedure_code character varying(20),
    description character varying(255),
    total_ortho_amt numeric(12,2),
    ins_share_amt numeric(12,2),
    pat_share_amt numeric(12,2),
    treat_start_date date,
    treat_end_date date,
    banding_date date,
    ins_plan_id integer,
    ins_setup_date date,
    ins_plan_amount numeric(12,2),
    ins_down_pay numeric(12,2),
    ins_interval character varying(20),
    ins_num_payments integer,
    ins_periodic_amt numeric(12,2),
    ins_rem_payments integer,
    ins_rem_amt numeric(12,2),
    ins_first_due_date date,
    ins_months_remaining integer,
    ins_notes text,
    pat_amt_financed numeric(12,2),
    pat_down_pay numeric(12,2),
    pat_apr numeric(6,4),
    pat_fin_charge numeric(12,2),
    pat_interval character varying(20),
    pat_num_payments integer,
    pat_periodic_amt numeric(12,2),
    pat_rem_payments integer,
    pat_rem_amt numeric(12,2),
    pat_first_due_date date,
    sec_ins_plan_id integer,
    sec_ins_plan_amount numeric(12,2),
    sec_ins_periodic_amt numeric(12,2),
    sec_ins_notes text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100),
    updated_at timestamp without time zone,
    initial_procedure_code character varying(20),
    pref_provider_id character varying(50),
    insert_class character varying(50),
    pat_setup_date date,
    pat_notes text,
    remarks text,
    financial_disclosure character varying(100),
    payment_code character varying(50),
    payment_token_id character varying(100),
    card_holder_name character varying(100),
    card_last4 character varying(4),
    card_exp_month integer,
    card_exp_year integer,
    ins_mon_claim_print_fee numeric(12,2),
    sec_ins_mon_claim_print_fee numeric(12,2),
    sec_ins_setup_date date,
    sec_ins_down_pay numeric(12,2),
    sec_ins_interval character varying(20),
    sec_ins_num_payments integer,
    sec_ins_rem_payments integer,
    sec_ins_rem_amt numeric(12,2),
    sec_ins_first_due_date date,
    sec_ins_months_remaining integer,
    tx_duration_months integer,
    months_remaining integer,
    created_by_id integer,
    updated_by integer,
    created_office_id integer,
    post_down_payment_with_card boolean DEFAULT false NOT NULL,
    ins_suppress_periodic_printing boolean DEFAULT false NOT NULL,
    sec_ins_suppress_periodic_printing boolean DEFAULT false NOT NULL
);


--
-- Name: ortho_plans_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ortho_plans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ortho_plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ortho_plans_id_seq OWNED BY public.ortho_plans.id;


--
-- Name: patient_adjustments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_adjustments (
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    provider_id character varying(50),
    procedure_id character varying(50),
    adjustment_date date NOT NULL,
    amount numeric(12,2) NOT NULL,
    adjustment_type character varying(50),
    notes text,
    is_void boolean NOT NULL,
    created_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    write_off_type character varying(20)
);


--
-- Name: patient_adjustments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_adjustments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_adjustments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_adjustments_id_seq OWNED BY public.patient_adjustments.id;


--
-- Name: patient_alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_alerts (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    legacy_id character varying(20),
    alert text NOT NULL,
    blocks_charges boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    deactivated_on timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer,
    is_flash_alert boolean DEFAULT false NOT NULL,
    source_medical_alert_id integer
);


--
-- Name: patient_alerts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_alerts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_alerts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_alerts_id_seq OWNED BY public.patient_alerts.id;


--
-- Name: patient_consents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_consents (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    template_id integer,
    plan_id character varying(50),
    title character varying(255),
    rendered_html text,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    signature_data text,
    document_id integer,
    signed_by integer,
    signed_at timestamp without time zone,
    is_deleted boolean DEFAULT false NOT NULL,
    created_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    signer_name character varying(255),
    signer_relationship character varying(50),
    signature_method character varying(20),
    declined_reason character varying(500),
    sig_string text,
    sig_format character varying(24),
    sig_compression smallint,
    sig_encryption smallint,
    point_count integer,
    stroke_count integer,
    device_vendor character varying(20),
    device_model character varying(40),
    device_serial character varying(40),
    captured_user_agent character varying(255),
    device_source character varying(20),
    content_hash character varying(64),
    signed_document_id integer,
    captured_at timestamp without time zone,
    signed_at_source character varying(10),
    signed_rendered_html text
);


--
-- Name: patient_consents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_consents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_consents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_consents_id_seq OWNED BY public.patient_consents.id;


--
-- Name: patient_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_documents (
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    document_type character varying(50),
    file_name character varying(500) NOT NULL,
    content_type character varying(100),
    file_size bigint,
    file_path character varying(500) NOT NULL,
    file_url character varying(500) NOT NULL,
    description character varying(500),
    is_deleted boolean NOT NULL,
    created_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    storage_backend character varying(20) DEFAULT 'local'::character varying NOT NULL,
    storage_bucket character varying(255),
    storage_path character varying(500),
    procedure_id character varying(50),
    claim_id character varying(50)
);


--
-- Name: patient_documents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_documents_id_seq OWNED BY public.patient_documents.id;


--
-- Name: patient_emergency_contacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_emergency_contacts (
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    name character varying(255) NOT NULL,
    relationship character varying(50),
    phone character varying(20),
    email character varying(255),
    is_active boolean NOT NULL,
    created_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    is_primary boolean DEFAULT false NOT NULL
);


--
-- Name: patient_emergency_contacts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_emergency_contacts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_emergency_contacts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_emergency_contacts_id_seq OWNED BY public.patient_emergency_contacts.id;


--
-- Name: patient_ins_payment_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_ins_payment_plans (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    legacy_plan_id character varying(20),
    periodic_order integer,
    periodic_date date,
    periodic_amt numeric(12,2),
    is_billed boolean DEFAULT false NOT NULL,
    billing_code character varying(50),
    ledger_id character varying(20),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100),
    plan_amount numeric(12,2),
    down_payment numeric(12,2),
    rem_total_amt numeric(12,2),
    rem_payments integer,
    ortho_plan_id integer
);


--
-- Name: patient_ins_payment_plans_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_ins_payment_plans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_ins_payment_plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_ins_payment_plans_id_seq OWNED BY public.patient_ins_payment_plans.id;


--
-- Name: patient_insurance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_insurance (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    ins_plan_id integer,
    subscriber_id integer,
    legacy_plan_type character varying(5),
    insurance_type character varying(20) NOT NULL,
    relationship character varying(50),
    deductible_remaining numeric(10,2),
    max_remaining numeric(10,2),
    ortho_remaining numeric(10,2),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    sec_sub_rel_to_prim_sub character varying(50),
    dentical_share_month integer,
    dentical_share_year integer,
    dentical_share_amount numeric(10,2),
    dentical_unused numeric(10,2),
    legacy_id character varying(50)
);


--
-- Name: patient_insurance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_insurance_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_insurance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_insurance_id_seq OWNED BY public.patient_insurance.id;


--
-- Name: patient_medical_alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_medical_alerts (
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    alert_code character varying(100) NOT NULL,
    alert_label character varying(255),
    response character varying(10),
    comments text,
    is_active boolean NOT NULL,
    created_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    updated_by integer,
    answered_at timestamp without time zone,
    section character varying(100),
    is_flash_alert boolean,
    blocks_charges boolean
);


--
-- Name: patient_medical_alerts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_medical_alerts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_medical_alerts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_medical_alerts_id_seq OWNED BY public.patient_medical_alerts.id;


--
-- Name: patient_medical_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_medical_history (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    comments text,
    alerts_completed_at timestamp without time zone,
    alerts_completed_by integer,
    dental_completed_at timestamp without time zone,
    dental_completed_by integer,
    medical_completed_at timestamp without time zone,
    medical_completed_by integer,
    last_signature_id integer,
    last_version_id integer,
    copied_from_patient_id integer,
    copied_at timestamp without time zone,
    copied_by integer,
    created_by integer,
    updated_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: patient_medical_history_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_medical_history_events (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    entity_type character varying(20) NOT NULL,
    entity_id integer,
    code character varying(50),
    label text,
    action character varying(20) NOT NULL,
    old_value text,
    new_value text,
    source_patient_id integer,
    changed_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: patient_medical_history_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_medical_history_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_medical_history_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_medical_history_events_id_seq OWNED BY public.patient_medical_history_events.id;


--
-- Name: patient_medical_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_medical_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_medical_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_medical_history_id_seq OWNED BY public.patient_medical_history.id;


--
-- Name: patient_notes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_notes (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    note_date date,
    note_type character varying(20),
    notes text NOT NULL,
    notes_html text,
    is_archived boolean DEFAULT false NOT NULL,
    is_deleted boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer,
    updated_at timestamp without time zone,
    updated_by integer,
    document_id integer
);


--
-- Name: patient_notes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_notes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_notes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_notes_id_seq OWNED BY public.patient_notes.id;


--
-- Name: patient_opening_balances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_opening_balances (
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    as_of_date date,
    current numeric(12,2) NOT NULL,
    over_30 numeric(12,2) NOT NULL,
    over_60 numeric(12,2) NOT NULL,
    over_90 numeric(12,2) NOT NULL,
    over_120 numeric(12,2) NOT NULL,
    notes text,
    created_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: patient_opening_balances_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_opening_balances_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_opening_balances_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_opening_balances_id_seq OWNED BY public.patient_opening_balances.id;


--
-- Name: patient_payment_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_payment_plans (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    plan_bal_amt numeric(12,2),
    tx_plan_number character varying(50),
    setup_date date,
    amt_financed numeric(12,2),
    down_payment numeric(12,2),
    apr numeric(6,4),
    fin_charge numeric(12,2),
    interval_type character varying(20),
    num_payments integer,
    periodic_amt numeric(12,2),
    first_due_date date,
    rem_payments integer,
    rem_total_amt numeric(12,2),
    notes text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100),
    updated_at timestamp without time zone,
    plan_type character varying(20) DEFAULT 'regular'::character varying NOT NULL,
    tx_plan_amt numeric(12,2),
    treatment_plan_id character varying(50),
    billing_code character varying(50),
    financial_disclosure character varying(100),
    payment_code character varying(50),
    payment_token_id character varying(100),
    card_holder_name character varying(100),
    card_last4 character varying(4),
    card_exp_month integer,
    card_exp_year integer,
    total_of_payments numeric(12,2),
    created_by_id integer,
    updated_by integer,
    post_down_payment_with_card boolean DEFAULT false NOT NULL
);


--
-- Name: patient_payment_plans_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_payment_plans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_payment_plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_payment_plans_id_seq OWNED BY public.patient_payment_plans.id;


--
-- Name: patient_payments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_payments (
    id character varying(50) NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    is_archived boolean DEFAULT false NOT NULL,
    payment_date date NOT NULL,
    amount numeric(12,2) NOT NULL,
    payment_type character varying(20) NOT NULL,
    payment_method character varying(50),
    check_number character varying(100),
    provider_id character varying(50),
    notes text,
    is_void boolean DEFAULT false NOT NULL,
    created_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    bank_number character varying(100),
    created_by_legacy character varying(50),
    updated_at timestamp without time zone,
    updated_by integer,
    eob_number character varying(50),
    eft_trace_number character varying(100),
    created_office_id integer
);


--
-- Name: patient_plan_installments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_plan_installments (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    plan_side character varying(10) DEFAULT 'patient'::character varying NOT NULL,
    ortho_plan_id integer,
    payment_plan_id integer,
    periodic_order integer,
    periodic_date date,
    periodic_amt numeric(12,2),
    plan_amount numeric(12,2),
    down_payment numeric(12,2),
    rem_total_amt numeric(12,2),
    rem_payments integer,
    is_billed boolean DEFAULT false NOT NULL,
    billing_code character varying(50),
    ledger_id character varying(50),
    created_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: patient_plan_installments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_plan_installments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_plan_installments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_plan_installments_id_seq OWNED BY public.patient_plan_installments.id;


--
-- Name: patient_procedures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_procedures (
    id character varying(50) NOT NULL,
    patient_id integer NOT NULL,
    appointment_id character varying(50),
    procedure_code character varying(20) NOT NULL,
    legacy_id character varying(20),
    is_archived boolean DEFAULT false NOT NULL,
    date_of_service date NOT NULL,
    provider_id character varying(50) NOT NULL,
    office_id integer NOT NULL,
    tooth character varying(10),
    surface character varying(20),
    quadrant character varying(10),
    fee numeric(12,2) NOT NULL,
    ucr_fee numeric(12,2),
    insurance_estimate numeric(12,2) DEFAULT 0 NOT NULL,
    patient_estimate numeric(12,2) DEFAULT 0 NOT NULL,
    apply_to character varying(5),
    billing_order character varying(10),
    resp_type character varying(10),
    billing_status character varying(30) DEFAULT 'not_billed'::character varying NOT NULL,
    claim_id character varying(50),
    hold_claim boolean DEFAULT false NOT NULL,
    is_void boolean DEFAULT false NOT NULL,
    material_id integer,
    notes text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer,
    treatment_plan_id character varying(50),
    hygienist_id character varying(50),
    created_by_legacy character varying(50),
    duration_minutes integer,
    updated_at timestamp without time zone,
    updated_by integer,
    fee_schedule_id integer,
    pat_paid numeric(12,2),
    pat_adjust numeric(12,2),
    treatment_plan_item_id character varying(50),
    diagnosis_pointers character varying(4),
    quantity integer DEFAULT 1 NOT NULL,
    fee_source character varying(24),
    fee_effective_date date,
    fee_override_reason character varying(255),
    coverage_pct numeric(5,2),
    coverage_rule_id integer,
    estimated_deductible numeric(12,2),
    sec_insurance_estimate numeric(12,2)
);


--
-- Name: patient_questionnaire_responses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_questionnaire_responses (
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    questionnaire_type character varying(20) NOT NULL,
    question_code character varying(100) NOT NULL,
    question_text text,
    answer text,
    is_active boolean NOT NULL,
    created_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    updated_by integer,
    answered_at timestamp without time zone
);


--
-- Name: patient_questionnaire_responses_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_questionnaire_responses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_questionnaire_responses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_questionnaire_responses_id_seq OWNED BY public.patient_questionnaire_responses.id;


--
-- Name: patient_recalls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_recalls (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    recall_type character varying(50),
    procedure_code character varying(20),
    due_date date,
    interval_months integer,
    last_completed date,
    status character varying(20) DEFAULT 'due'::character varying NOT NULL,
    notes text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer,
    updated_at timestamp without time zone,
    interval_unit character varying(10),
    scheduled_date date,
    scheduled_time character varying(10)
);


--
-- Name: patient_recalls_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_recalls_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_recalls_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_recalls_id_seq OWNED BY public.patient_recalls.id;


--
-- Name: patient_refunds; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_refunds (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    refund_date date NOT NULL,
    amount numeric(12,2) NOT NULL,
    refund_method character varying(50),
    reason character varying(255),
    reason_code character varying(50),
    source_payment_id character varying(50),
    reversed_type character varying(20),
    reversed_id character varying(50),
    check_number character varying(100),
    reference_number character varying(100),
    authorized_by integer,
    notes text,
    is_void boolean DEFAULT false NOT NULL,
    created_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: patient_refunds_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_refunds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_refunds_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_refunds_id_seq OWNED BY public.patient_refunds.id;


--
-- Name: patient_reg_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_reg_plans (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    setup_date date,
    amt_financed numeric(12,2),
    down_payment numeric(12,2),
    apr numeric(6,4),
    fin_charge numeric(12,2),
    interval_type character varying(20),
    num_payments integer,
    periodic_amt numeric(12,2),
    first_due_date date,
    rem_payments integer,
    rem_total_amt numeric(12,2),
    notes text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100)
);


--
-- Name: patient_reg_plans_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_reg_plans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_reg_plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_reg_plans_id_seq OWNED BY public.patient_reg_plans.id;


--
-- Name: patient_sec_ins_payment_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_sec_ins_payment_plans (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    legacy_plan_id character varying(20),
    periodic_order integer,
    periodic_date date,
    periodic_amt numeric(12,2),
    is_billed boolean DEFAULT false NOT NULL,
    billing_code character varying(50),
    ledger_id character varying(20),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100),
    plan_amount numeric(12,2),
    down_payment numeric(12,2),
    rem_total_amt numeric(12,2),
    rem_payments integer,
    ortho_plan_id integer
);


--
-- Name: patient_sec_ins_payment_plans_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_sec_ins_payment_plans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_sec_ins_payment_plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_sec_ins_payment_plans_id_seq OWNED BY public.patient_sec_ins_payment_plans.id;


--
-- Name: patient_signatures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_signatures (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    legacy_id character varying(20),
    signature_data text,
    signature_len integer,
    device_source character varying(20),
    is_user_sig boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer,
    signature_type character varying(30),
    signed_at timestamp without time zone,
    signed_by_user_id integer,
    content_hash character varying(64),
    is_active boolean DEFAULT true NOT NULL,
    superseded_by_id integer,
    voided_at timestamp without time zone,
    voided_by integer,
    updated_at timestamp without time zone,
    updated_by integer,
    sig_string text,
    sig_format character varying(24),
    sig_compression smallint,
    sig_encryption smallint,
    point_count integer,
    stroke_count integer,
    device_vendor character varying(20),
    device_model character varying(40),
    device_serial character varying(40),
    captured_user_agent character varying(255),
    progress_note_id integer,
    consent_id integer,
    claim_id character varying(50),
    signer_name character varying(120),
    signer_relationship character varying(40),
    signer_provider_id character varying(50)
);


--
-- Name: patient_signatures_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_signatures_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_signatures_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_signatures_id_seq OWNED BY public.patient_signatures.id;


--
-- Name: patient_statements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_statements (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    statement_date date NOT NULL,
    period_start date,
    period_end date,
    opening_balance numeric(12,2) DEFAULT '0'::numeric NOT NULL,
    total_charges numeric(12,2) DEFAULT '0'::numeric NOT NULL,
    total_payments numeric(12,2) DEFAULT '0'::numeric NOT NULL,
    total_adjustments numeric(12,2) DEFAULT '0'::numeric NOT NULL,
    closing_balance numeric(12,2) DEFAULT '0'::numeric NOT NULL,
    aging_current numeric(12,2) DEFAULT '0'::numeric NOT NULL,
    aging_30 numeric(12,2) DEFAULT '0'::numeric NOT NULL,
    aging_60 numeric(12,2) DEFAULT '0'::numeric NOT NULL,
    aging_90 numeric(12,2) DEFAULT '0'::numeric NOT NULL,
    aging_120 numeric(12,2) DEFAULT '0'::numeric NOT NULL,
    message character varying(500),
    batch_id character varying(50),
    delivery_method character varying(20),
    delivery_status character varying(20) DEFAULT 'generated'::character varying NOT NULL,
    delivered_to character varying(255),
    delivered_at date,
    snapshot json,
    created_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: patient_statements_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_statements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_statements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_statements_id_seq OWNED BY public.patient_statements.id;


--
-- Name: patients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patients (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    home_office_id integer,
    legacy_id character varying(20),
    chart_no character varying(50),
    first_name character varying(100),
    last_name character varying(100),
    preferred_name character varying(100),
    title character varying(20),
    middle_initial character varying(10),
    dob date,
    gender character varying(20),
    ssn character varying(20),
    marital_status character varying(20),
    phone character varying(20),
    cell_phone character varying(20),
    work_phone character varying(20),
    email character varying(255),
    preferred_contact character varying(50),
    address_line1 character varying(255),
    address_line2 character varying(255),
    city character varying(100),
    state character varying(50),
    zip character varying(20),
    preferred_provider_id character varying(50),
    preferred_language character varying(50) DEFAULT 'English'::character varying NOT NULL,
    first_visit date,
    last_visit date,
    next_recall date,
    is_finance_charge boolean DEFAULT false NOT NULL,
    send_statements boolean DEFAULT true NOT NULL,
    send_collections boolean DEFAULT false NOT NULL,
    no_auto_email boolean DEFAULT false NOT NULL,
    no_auto_sms boolean DEFAULT false NOT NULL,
    is_locked boolean DEFAULT false NOT NULL,
    hipaa_agreement boolean DEFAULT false NOT NULL,
    guardian_name character varying(255),
    guardian_phone character varying(20),
    referral_type character varying(50),
    referred_by character varying(255),
    patient_notes text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    created_by integer,
    responsible_party_id character varying(50),
    patient_type character varying(50),
    medicaid_id character varying(50),
    pronouns character varying(20),
    driver_license character varying(50),
    student_status character varying(20),
    school_name character varying(255),
    preferred_hygienist_id character varying(50),
    referred_to character varying(255),
    responsible_party_relationship character varying(50),
    referral_to_date date,
    hipaa_sharing_notes text,
    patient_types json,
    fee_schedule_id integer,
    assign_benefits boolean DEFAULT false NOT NULL,
    add_to_quickfill boolean DEFAULT false NOT NULL,
    no_correspondence boolean DEFAULT false NOT NULL,
    photo_document_id integer,
    updated_by integer,
    sms_opt_out_at timestamp without time zone,
    sms_opt_in_at timestamp without time zone,
    middle_name character varying(50),
    suffix character varying(10)
);


--
-- Name: patients_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patients_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patients_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patients_id_seq OWNED BY public.patients.id;


--
-- Name: payment_allocations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payment_allocations (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    legacy_id character varying(20),
    procedure_id character varying(50),
    payment_id character varying(50),
    claim_id character varying(50),
    ins_plan_id integer,
    provider_id character varying(50),
    alloc_date date,
    amount numeric(12,2) NOT NULL,
    alloc_type character varying(5),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    adjustment_id integer
);


--
-- Name: payment_allocations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.payment_allocations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: payment_allocations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.payment_allocations_id_seq OWNED BY public.payment_allocations.id;


--
-- Name: perio_chart_activity; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.perio_chart_activity (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    activity_date date,
    perio_type character varying(50),
    orientation character varying(10),
    arch character varying(10),
    quadrant character varying(10),
    tooth_no character varying(10),
    block_no character varying(20),
    add_info text,
    mxy character varying(50),
    perio_value character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100)
);


--
-- Name: perio_chart_activity_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.perio_chart_activity_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: perio_chart_activity_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.perio_chart_activity_id_seq OWNED BY public.perio_chart_activity.id;


--
-- Name: perio_chart_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.perio_chart_settings (
    id integer NOT NULL,
    user_id integer NOT NULL,
    is_forward boolean DEFAULT true NOT NULL,
    is_indicator boolean DEFAULT true NOT NULL,
    is_mgj boolean DEFAULT true NOT NULL,
    pd_level integer DEFAULT 4 NOT NULL,
    bp_level integer DEFAULT 2 NOT NULL,
    ip_level integer DEFAULT 3 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: perio_chart_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.perio_chart_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: perio_chart_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.perio_chart_settings_id_seq OWNED BY public.perio_chart_settings.id;


--
-- Name: perio_chart_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.perio_chart_templates (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(100) NOT NULL,
    show_mgj boolean DEFAULT false NOT NULL,
    pd_warning_level integer DEFAULT 4 NOT NULL,
    cal_warning_level integer DEFAULT 4 NOT NULL,
    bp_level integer DEFAULT 2 NOT NULL,
    ip_level integer DEFAULT 3 NOT NULL,
    fgm_level integer DEFAULT 2 NOT NULL,
    start_voice boolean DEFAULT false NOT NULL,
    auto_advance json,
    created_by integer,
    updated_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: perio_chart_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.perio_chart_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: perio_chart_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.perio_chart_templates_id_seq OWNED BY public.perio_chart_templates.id;


--
-- Name: perio_exam_details; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.perio_exam_details (
    id integer NOT NULL,
    exam_id integer NOT NULL,
    tooth_no character varying(10) NOT NULL,
    pd1 integer,
    pd2 integer,
    pd3 integer,
    pd4 integer,
    pd5 integer,
    pd6 integer,
    fgm1 integer,
    fgm2 integer,
    fgm3 integer,
    fgm4 integer,
    fgm5 integer,
    fgm6 integer,
    mgj1 integer,
    mgj2 integer,
    mgj3 integer,
    mgj4 integer,
    mgj5 integer,
    mgj6 integer,
    bleed1 boolean,
    bleed2 boolean,
    bleed3 boolean,
    bleed4 boolean,
    bleed5 boolean,
    bleed6 boolean,
    supp1 boolean,
    supp2 boolean,
    supp3 boolean,
    supp4 boolean,
    supp5 boolean,
    supp6 boolean,
    furc1 integer,
    furc2 integer,
    furc3 integer,
    furc4 integer,
    furc5 integer,
    furc6 integer,
    mobility_buccal numeric(2,1),
    mobility_lingual numeric(2,1),
    cal1 integer,
    cal2 integer,
    cal3 integer,
    cal4 integer,
    cal5 integer,
    cal6 integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    created_by integer,
    updated_by integer
);


--
-- Name: perio_exam_details_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.perio_exam_details_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: perio_exam_details_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.perio_exam_details_id_seq OWNED BY public.perio_exam_details.id;


--
-- Name: perio_exams; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.perio_exams (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    exam_date date NOT NULL,
    notes text,
    is_voided boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer,
    updated_at timestamp without time zone,
    updated_by integer,
    provider_id character varying(50)
);


--
-- Name: perio_exams_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.perio_exams_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: perio_exams_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.perio_exams_id_seq OWNED BY public.perio_exams.id;


--
-- Name: permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.permissions (
    code character varying(255) NOT NULL,
    label character varying(255) NOT NULL,
    category character varying(100),
    is_active boolean NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: permissions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.permissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: permissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.permissions_id_seq OWNED BY public.permissions.id;


--
-- Name: place_of_service_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.place_of_service_codes (
    tenant_id integer NOT NULL,
    code character varying(10) NOT NULL,
    type character varying(100),
    name character varying(255),
    tax_id character varying(50),
    office_id integer,
    is_active boolean NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: place_of_service_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.place_of_service_codes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: place_of_service_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.place_of_service_codes_id_seq OWNED BY public.place_of_service_codes.id;


--
-- Name: postcard_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.postcard_templates (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    name character varying(255) NOT NULL,
    card_type character varying(10),
    body text,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: postcard_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.postcard_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: postcard_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.postcard_templates_id_seq OWNED BY public.postcard_templates.id;


--
-- Name: prescription_library; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prescription_library (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    drug_name character varying(255) NOT NULL,
    dispense character varying(255),
    sig character varying(500),
    refills integer DEFAULT 0 NOT NULL,
    is_as_written boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    updated_by integer,
    created_by integer,
    allergy_keys json
);


--
-- Name: prescription_library_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.prescription_library_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: prescription_library_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.prescription_library_id_seq OWNED BY public.prescription_library.id;


--
-- Name: prescriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prescriptions (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    library_rx_id integer,
    rx_date date,
    drug_name character varying(255) NOT NULL,
    dispense character varying(255),
    sig character varying(500),
    refills integer DEFAULT 0 NOT NULL,
    is_as_written boolean DEFAULT false NOT NULL,
    provider_id character varying(50),
    notes text,
    is_active boolean DEFAULT true NOT NULL,
    dosespot_rx_id character varying(50),
    dosespot_status character varying(50),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer,
    alerts_acknowledged boolean DEFAULT false NOT NULL,
    acknowledged_alert_ids json,
    acknowledged_alerts json,
    alert_warnings json,
    alerts_acknowledged_at timestamp without time zone,
    alerts_acknowledged_by integer
);


--
-- Name: prescriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.prescriptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: prescriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.prescriptions_id_seq OWNED BY public.prescriptions.id;


--
-- Name: procedure_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.procedure_codes (
    code character varying(20) NOT NULL,
    legacy_code character varying(20),
    description character varying(500) NOT NULL,
    category character varying(100) NOT NULL,
    default_fee numeric(10,2) DEFAULT 0 NOT NULL,
    default_duration_minutes integer,
    requires_tooth boolean DEFAULT false NOT NULL,
    requires_surface boolean DEFAULT false NOT NULL,
    requires_quadrant boolean DEFAULT false NOT NULL,
    requires_lab boolean DEFAULT false NOT NULL,
    is_ortho boolean DEFAULT false NOT NULL,
    billing_order character varying(10),
    recall_interval integer,
    recall_unit character varying(10),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    chart_category character varying(100),
    tooth_area character varying(50),
    draw_as character varying(50),
    min_surfaces integer,
    max_surfaces integer,
    default_material_id integer,
    valid_teeth json,
    taxable boolean DEFAULT false,
    sales_tax_code character varying(50),
    visit_code character varying(50),
    ledger_code character varying(50),
    ar_code character varying(50),
    is_post_op boolean DEFAULT false,
    exempt_from_dental_max boolean DEFAULT false,
    lock_default_provider boolean DEFAULT false,
    default_provider_id character varying(50),
    default_notes_macro_id integer,
    show_ada_code_in_notes boolean DEFAULT false,
    nhs_treatment_category character varying(100),
    nhs_clinical_data_set character varying(100),
    amb_code character varying(20),
    is_downgrade boolean DEFAULT false NOT NULL,
    alternate_of character varying(20),
    anatomy_rules json,
    surface_rules json,
    material_rules json,
    coverage_category character varying(20),
    requires_attachment boolean DEFAULT false NOT NULL,
    requires_perio_chart boolean DEFAULT false NOT NULL,
    requires_photo boolean DEFAULT false NOT NULL,
    requires_xray boolean DEFAULT false NOT NULL,
    requires_missing_tooth_info boolean DEFAULT false NOT NULL
);


--
-- Name: procedure_fee_provenance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.procedure_fee_provenance (
    id integer NOT NULL,
    procedure_id character varying(50) NOT NULL,
    fee_schedule_id integer,
    fee_schedule_legacy_id character varying(20),
    fee_effective_date date,
    legacy_ledger_id character varying(50),
    contracted_amount numeric(12,2),
    prim_ins_plan_legacy_id character varying(20),
    prim_estimated numeric(12,2),
    prim_deductible numeric(12,2),
    prim_max_consumed numeric(12,2),
    sec_estimated numeric(12,2),
    sec_deductible numeric(12,2),
    ter_estimated numeric(12,2),
    ter_deductible numeric(12,2),
    quad_estimated numeric(12,2),
    quad_deductible numeric(12,2),
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: procedure_fee_provenance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.procedure_fee_provenance_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: procedure_fee_provenance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.procedure_fee_provenance_id_seq OWNED BY public.procedure_fee_provenance.id;


--
-- Name: procedure_insurance_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.procedure_insurance_rules (
    tenant_id integer NOT NULL,
    procedure_code character varying(20) NOT NULL,
    coverage_pct numeric(5,2),
    frequency_limit character varying(50),
    age_limit character varying(50),
    wait_period character varying(50),
    notes text,
    is_active boolean NOT NULL,
    created_by integer,
    updated_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: procedure_insurance_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.procedure_insurance_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: procedure_insurance_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.procedure_insurance_rules_id_seq OWNED BY public.procedure_insurance_rules.id;


--
-- Name: production_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.production_types (
    tenant_id integer NOT NULL,
    name character varying(100) NOT NULL,
    color character varying(50),
    description text,
    appointnow_visible boolean NOT NULL,
    appointnow_duration integer,
    is_inactive boolean NOT NULL,
    is_active boolean NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: production_types_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.production_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: production_types_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.production_types_id_seq OWNED BY public.production_types.id;


--
-- Name: progress_note_attachments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.progress_note_attachments (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    progress_note_id integer NOT NULL,
    attachment_type character varying(50),
    file_name character varying(500) NOT NULL,
    content_type character varying(100),
    file_size bigint,
    file_path character varying(500) NOT NULL,
    file_url character varying(500) NOT NULL,
    description character varying(500),
    is_deleted boolean DEFAULT false NOT NULL,
    created_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: progress_note_attachments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.progress_note_attachments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: progress_note_attachments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.progress_note_attachments_id_seq OWNED BY public.progress_note_attachments.id;


--
-- Name: progress_notes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.progress_notes (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    note_date date,
    notes text,
    notes_html text,
    tooth character varying(255),
    is_deleted boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer,
    surface character varying(50),
    region character varying(50),
    signed_by integer,
    signed_at timestamp without time zone,
    is_struck_off boolean DEFAULT false NOT NULL,
    struck_off_at timestamp without time zone,
    struck_off_by integer,
    drawing_strokes json,
    drawing_doc_id integer,
    content_hash character varying(64),
    updated_at timestamp without time zone,
    updated_by integer
);


--
-- Name: progress_notes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.progress_notes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: progress_notes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.progress_notes_id_seq OWNED BY public.progress_notes.id;


--
-- Name: provider_carrier_logins; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provider_carrier_logins (
    tenant_id integer NOT NULL,
    provider_id character varying(50) NOT NULL,
    carrier_id integer,
    portal_name character varying(255),
    portal_url character varying(500),
    username character varying(255),
    password_enc text,
    notes text,
    is_active boolean NOT NULL,
    created_by integer,
    updated_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: provider_carrier_logins_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.provider_carrier_logins_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: provider_carrier_logins_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.provider_carrier_logins_id_seq OWNED BY public.provider_carrier_logins.id;


--
-- Name: provider_holidays; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provider_holidays (
    tenant_id integer NOT NULL,
    provider_id character varying(50) NOT NULL,
    holiday_date date NOT NULL,
    holiday_name character varying(255) NOT NULL,
    status character varying(20),
    holiday_type character varying(20),
    is_recurring boolean NOT NULL,
    created_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: provider_holidays_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.provider_holidays_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: provider_holidays_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.provider_holidays_id_seq OWNED BY public.provider_holidays.id;


--
-- Name: provider_insurance_ids; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provider_insurance_ids (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    provider_id character varying(50) NOT NULL,
    carrier_id integer NOT NULL,
    ins_id character varying(100),
    in_network boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100)
);


--
-- Name: provider_insurance_ids_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.provider_insurance_ids_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: provider_insurance_ids_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.provider_insurance_ids_id_seq OWNED BY public.provider_insurance_ids.id;


--
-- Name: provider_offices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provider_offices (
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    provider_id character varying(50) NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: provider_offices_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.provider_offices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: provider_offices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.provider_offices_id_seq OWNED BY public.provider_offices.id;


--
-- Name: provider_procedure_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provider_procedure_codes (
    tenant_id integer NOT NULL,
    provider_id character varying(50) NOT NULL,
    procedure_code character varying(20) NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: provider_procedure_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.provider_procedure_codes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: provider_procedure_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.provider_procedure_codes_id_seq OWNED BY public.provider_procedure_codes.id;


--
-- Name: provider_referral_offices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provider_referral_offices (
    tenant_id integer NOT NULL,
    provider_id character varying(50) NOT NULL,
    office_id integer NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: provider_referral_offices_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.provider_referral_offices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: provider_referral_offices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.provider_referral_offices_id_seq OWNED BY public.provider_referral_offices.id;


--
-- Name: provider_route_slips; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provider_route_slips (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    provider_id character varying(50) NOT NULL,
    legacy_id character varying(20),
    procedure_code character varying(20),
    num_times integer DEFAULT 1 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100)
);


--
-- Name: provider_route_slips_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.provider_route_slips_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: provider_route_slips_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.provider_route_slips_id_seq OWNED BY public.provider_route_slips.id;


--
-- Name: provider_schedule_days; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provider_schedule_days (
    tenant_id integer NOT NULL,
    provider_id character varying(50) NOT NULL,
    office_id integer,
    day_of_week integer NOT NULL,
    is_closed boolean NOT NULL,
    start_time time without time zone,
    end_time time without time zone,
    lunch_start time without time zone,
    lunch_end time without time zone,
    effective_from date,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: provider_schedule_days_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.provider_schedule_days_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: provider_schedule_days_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.provider_schedule_days_id_seq OWNED BY public.provider_schedule_days.id;


--
-- Name: provider_signatures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provider_signatures (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    provider_id character varying(50) NOT NULL,
    signature_data text,
    signature_len integer,
    device_source character varying(20),
    signed_at timestamp without time zone,
    sig_string text,
    sig_format character varying(24),
    sig_compression smallint,
    sig_encryption smallint,
    point_count integer,
    stroke_count integer,
    device_vendor character varying(20),
    device_model character varying(40),
    device_serial character varying(40),
    captured_user_agent character varying(255),
    updated_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: provider_signatures_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.provider_signatures_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: provider_signatures_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.provider_signatures_id_seq OWNED BY public.provider_signatures.id;


--
-- Name: provider_watermarks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provider_watermarks (
    tenant_id integer NOT NULL,
    provider_id character varying(50) NOT NULL,
    is_enabled boolean NOT NULL,
    watermark_image_url character varying(500),
    signature_image_url character varying(500),
    opacity integer,
    "position" character varying(30),
    updated_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: provider_watermarks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.provider_watermarks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: provider_watermarks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.provider_watermarks_id_seq OWNED BY public.provider_watermarks.id;


--
-- Name: providers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.providers (
    id character varying(50) NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(255) NOT NULL,
    title character varying(20),
    short_id character varying(20),
    role character varying(50) DEFAULT 'dentist'::character varying NOT NULL,
    npi character varying(50),
    license character varying(100),
    tax_id character varying(50),
    dea_id character varying(50),
    specialty character varying(100),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    first_name character varying(100),
    last_name character varying(100),
    created_by integer,
    user_id integer,
    scheduler_color character varying(20),
    is_ortho_provider boolean DEFAULT false,
    visible_in_appointnow boolean DEFAULT false,
    default_provider_time integer,
    is_billing_provider boolean DEFAULT false,
    dosespot_user_id character varying(100),
    updox_direct_address character varying(255),
    denticon_user_id character varying(100),
    print_separate_claim_form boolean DEFAULT false,
    ortho_questionnaire_template character varying(100),
    custom_1 character varying(255),
    custom_2 character varying(255),
    address_line1 character varying(255),
    address_line2 character varying(255),
    city character varying(100),
    state character varying(50),
    zip character varying(20),
    phone character varying(20),
    email character varying(255),
    default_operatory_id character varying(50),
    taxonomy_code character varying(10)
);


--
-- Name: questionnaire_headers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.questionnaire_headers (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    description character varying(255) NOT NULL,
    is_multi_select boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    is_custom boolean DEFAULT false NOT NULL
);


--
-- Name: questionnaire_headers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.questionnaire_headers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: questionnaire_headers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.questionnaire_headers_id_seq OWNED BY public.questionnaire_headers.id;


--
-- Name: questionnaire_options; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.questionnaire_options (
    id integer NOT NULL,
    questionnaire_id integer NOT NULL,
    legacy_id character varying(20),
    answer_code character varying(20) NOT NULL,
    sort_order integer DEFAULT 1 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: questionnaire_options_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.questionnaire_options_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: questionnaire_options_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.questionnaire_options_id_seq OWNED BY public.questionnaire_options.id;


--
-- Name: referral_demog_details; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.referral_demog_details (
    id integer NOT NULL,
    referral_id integer,
    tenant_id integer NOT NULL,
    demog_header_id integer,
    legacy_id character varying(20),
    data text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100)
);


--
-- Name: referral_demog_details_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.referral_demog_details_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: referral_demog_details_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.referral_demog_details_id_seq OWNED BY public.referral_demog_details.id;


--
-- Name: referral_demog_headers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.referral_demog_headers (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(20),
    description character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100)
);


--
-- Name: referral_demog_headers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.referral_demog_headers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: referral_demog_headers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.referral_demog_headers_id_seq OWNED BY public.referral_demog_headers.id;


--
-- Name: referrals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.referrals (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    referral_type character varying(10),
    patient_id integer,
    first_name character varying(100),
    last_name character varying(100),
    address character varying(255),
    city character varying(100),
    state character varying(50),
    zip character varying(20),
    phone character varying(20),
    email character varying(255),
    npi character varying(50),
    specialty character varying(100),
    reason_code character varying(20),
    notes text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer,
    e_referral_id character varying(50),
    practice_name character varying(255),
    contact_name character varying(255),
    cost numeric(12,2)
);


--
-- Name: referrals_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.referrals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: referrals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.referrals_id_seq OWNED BY public.referrals.id;


--
-- Name: refresh_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.refresh_tokens (
    id integer NOT NULL,
    user_id integer NOT NULL,
    token_hash character varying(255) NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    revoked boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: refresh_tokens_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.refresh_tokens_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: refresh_tokens_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.refresh_tokens_id_seq OWNED BY public.refresh_tokens.id;


--
-- Name: responsible_parties; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.responsible_parties (
    tenant_id integer NOT NULL,
    title character varying(20),
    preferred_name character varying(100),
    last_name character varying(100),
    first_name character varying(100),
    middle_initial character varying(10),
    address_line1 character varying(255),
    address_line2 character varying(255),
    city character varying(100),
    state character varying(50),
    zip character varying(20),
    email character varying(255),
    dob date,
    marital_status character varying(20),
    sex character varying(20),
    ssn character varying(20),
    driver_license character varying(50),
    home_phone character varying(20),
    cell_phone character varying(20),
    work_phone character varying(20),
    employer character varying(255),
    resp_party_type character varying(20),
    collection_agency_id integer,
    send_statements boolean NOT NULL,
    no_email_statement boolean NOT NULL,
    send_collections boolean NOT NULL,
    is_finance_charge boolean NOT NULL,
    statement_message text,
    statement_message_print_count integer,
    financial_notes text,
    responsible_party_notes text,
    is_active boolean NOT NULL,
    created_by integer,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    legacy_id character varying(20),
    home_office_id integer,
    middle_name character varying(50),
    suffix character varying(10)
);


--
-- Name: responsible_parties_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.responsible_parties_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: responsible_parties_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.responsible_parties_id_seq OWNED BY public.responsible_parties.id;


--
-- Name: ringcentral_sms_subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ringcentral_sms_subscriptions (
    id integer NOT NULL,
    subscription_id character varying(64) NOT NULL,
    webhook_url character varying(500) NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    last_renewed_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: ringcentral_sms_subscriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ringcentral_sms_subscriptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ringcentral_sms_subscriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ringcentral_sms_subscriptions_id_seq OWNED BY public.ringcentral_sms_subscriptions.id;


--
-- Name: signature_audit_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.signature_audit_events (
    id integer NOT NULL,
    tenant_id integer,
    entity_type character varying(30) NOT NULL,
    entity_id integer NOT NULL,
    patient_id integer,
    event character varying(30) NOT NULL,
    actor_id integer,
    occurred_at timestamp without time zone,
    ip character varying(45),
    user_agent character varying(255),
    device_source character varying(20),
    device_vendor character varying(20),
    device_model character varying(40),
    device_serial character varying(40),
    signature_type character varying(30),
    content_hash character varying(64),
    reason character varying(500),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    signer_name character varying(120),
    signer_relationship character varying(40)
);


--
-- Name: signature_audit_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.signature_audit_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: signature_audit_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.signature_audit_events_id_seq OWNED BY public.signature_audit_events.id;


--
-- Name: sms_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sms_messages (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer,
    patient_id integer,
    appointment_id character varying(50),
    legacy_id character varying(20),
    sent_text text,
    sent_phone character varying(20),
    send_status character varying(50),
    delivered_on timestamp without time zone,
    reply_text text,
    reply_phone character varying(20),
    reply_received_on timestamp without time zone,
    message_type character varying(50),
    is_read boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by integer,
    twilio_sid character varying(34),
    reply_twilio_sid character varying(34),
    from_phone character varying(20),
    direction character varying(10),
    sent_at timestamp without time zone,
    error_code character varying(20),
    error_message text,
    segments smallint,
    client_id character varying(40),
    template_id integer,
    reply_intent character varying(20),
    needs_attention boolean DEFAULT false NOT NULL,
    candidate_patient_ids json,
    reminder_lead_hours smallint,
    inbound_payload_hash character varying(64),
    status_payload_hash character varying(64),
    updated_at timestamp without time zone
);


--
-- Name: sms_messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sms_messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sms_messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sms_messages_id_seq OWNED BY public.sms_messages.id;


--
-- Name: sms_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sms_templates (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer,
    name character varying(120) NOT NULL,
    message_type character varying(50) DEFAULT 'manual'::character varying NOT NULL,
    body text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_by integer,
    updated_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: sms_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sms_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sms_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sms_templates_id_seq OWNED BY public.sms_templates.id;


--
-- Name: stored_objects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stored_objects (
    id integer NOT NULL,
    tenant_id integer,
    bucket character varying(200) NOT NULL,
    object_key character varying(500) NOT NULL,
    kind character varying(20),
    content_type character varying(100),
    size_bytes bigint,
    sha256 character varying(64),
    md5_b64 character varying(32),
    crc32c character varying(16),
    storage_class character varying(20),
    ref_count integer DEFAULT 1 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: stored_objects_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.stored_objects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: stored_objects_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.stored_objects_id_seq OWNED BY public.stored_objects.id;


--
-- Name: support_tickets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.support_tickets (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    reporter_user_id integer,
    project_key character varying(20),
    summary character varying(500) NOT NULL,
    issue_type character varying(30),
    priority character varying(20),
    module character varying(50),
    description text,
    status character varying(30) DEFAULT 'Open'::character varying NOT NULL,
    jira_issue_key character varying(50),
    jira_issue_url character varying(500),
    context json,
    attachments json,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: support_tickets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.support_tickets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: support_tickets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.support_tickets_id_seq OWNED BY public.support_tickets.id;


--
-- Name: tenants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tenants (
    id integer NOT NULL,
    legacy_id character varying(20),
    name character varying(255) NOT NULL,
    code character varying(80) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: tenants_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tenants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tenants_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tenants_id_seq OWNED BY public.tenants.id;


--
-- Name: time_clock_entries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.time_clock_entries (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer,
    user_id integer NOT NULL,
    legacy_id character varying(20),
    clock_in timestamp without time zone NOT NULL,
    clock_out timestamp without time zone,
    total_hours numeric(5,2),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    entry_type character varying(20) DEFAULT 'work'::character varying NOT NULL,
    source character varying(20) DEFAULT 'manual'::character varying NOT NULL,
    clock_basis character varying(20) DEFAULT 'utc'::character varying NOT NULL,
    notes character varying(500),
    created_by integer,
    updated_at timestamp without time zone,
    updated_by integer,
    is_edited boolean DEFAULT false NOT NULL,
    original_clock_in timestamp without time zone,
    original_clock_out timestamp without time zone,
    edit_reason character varying(500),
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp without time zone,
    deleted_by integer,
    delete_reason character varying(500),
    auto_closed boolean DEFAULT false NOT NULL,
    auto_closed_at timestamp without time zone,
    auto_close_reason character varying(50)
);


--
-- Name: time_clock_entries_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.time_clock_entries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: time_clock_entries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.time_clock_entries_id_seq OWNED BY public.time_clock_entries.id;


--
-- Name: time_clock_entry_edits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.time_clock_entry_edits (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    entry_id integer NOT NULL,
    action character varying(20) NOT NULL,
    edited_by integer,
    edited_at timestamp without time zone NOT NULL,
    edit_reason character varying(500),
    original_clock_in timestamp without time zone,
    original_clock_out timestamp without time zone,
    new_clock_in timestamp without time zone,
    new_clock_out timestamp without time zone,
    changes json
);


--
-- Name: time_clock_entry_edits_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.time_clock_entry_edits_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: time_clock_entry_edits_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.time_clock_entry_edits_id_seq OWNED BY public.time_clock_entry_edits.id;


--
-- Name: time_clock_periods; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.time_clock_periods (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    office_id integer,
    period_start date NOT NULL,
    period_end date NOT NULL,
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    locked boolean DEFAULT false NOT NULL,
    approved_by integer,
    approved_at timestamp without time zone,
    locked_by integer,
    locked_at timestamp without time zone,
    notes text,
    created_by integer,
    updated_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: time_clock_periods_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.time_clock_periods_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: time_clock_periods_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.time_clock_periods_id_seq OWNED BY public.time_clock_periods.id;


--
-- Name: time_clock_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.time_clock_settings (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    overtime_method character varying(20) DEFAULT 'weekly'::character varying NOT NULL,
    daily_threshold_hours numeric(5,2) DEFAULT '8'::numeric NOT NULL,
    weekly_threshold_hours numeric(5,2) DEFAULT '40'::numeric NOT NULL,
    week_start_day character varying(10) DEFAULT 'sunday'::character varying NOT NULL,
    overtime_rate numeric(5,2) DEFAULT 1.5 NOT NULL,
    auto_close_after_hours integer DEFAULT 20 NOT NULL,
    auto_close_policy character varying(20) DEFAULT 'flag'::character varying NOT NULL,
    require_edit_reason boolean DEFAULT false NOT NULL,
    updated_by integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: time_clock_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.time_clock_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: time_clock_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.time_clock_settings_id_seq OWNED BY public.time_clock_settings.id;


--
-- Name: treatment_plan_insurance_details; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.treatment_plan_insurance_details (
    id integer NOT NULL,
    plan_item_id character varying(50) NOT NULL,
    ins_plan_id integer,
    legacy_id character varying(20),
    is_archived boolean DEFAULT false NOT NULL,
    billing_order character varying(10),
    estimated_ins numeric(12,2) DEFAULT 0 NOT NULL,
    estimated_pat numeric(12,2) DEFAULT 0 NOT NULL,
    deductible numeric(12,2),
    coverage_pct numeric(5,2),
    annual_max_rem numeric(12,2),
    preauth_number character varying(100),
    preauth_date date,
    preauth_expires date,
    preauth_amount numeric(12,2),
    notes text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    preauth_status character varying(20),
    preauth_status_at timestamp without time zone
);


--
-- Name: treatment_plan_insurance_details_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.treatment_plan_insurance_details_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: treatment_plan_insurance_details_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.treatment_plan_insurance_details_id_seq OWNED BY public.treatment_plan_insurance_details.id;


--
-- Name: treatment_plan_item_icd_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.treatment_plan_item_icd_codes (
    id integer NOT NULL,
    plan_item_id character varying(50) NOT NULL,
    icd_code_id integer NOT NULL,
    ordinal integer DEFAULT 1 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: treatment_plan_item_icd_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.treatment_plan_item_icd_codes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: treatment_plan_item_icd_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.treatment_plan_item_icd_codes_id_seq OWNED BY public.treatment_plan_item_icd_codes.id;


--
-- Name: treatment_plan_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.treatment_plan_items (
    id character varying(50) NOT NULL,
    plan_id character varying(50) NOT NULL,
    procedure_code character varying(20) NOT NULL,
    description character varying(500),
    tooth character varying(10),
    surface character varying(50),
    priority integer DEFAULT 1 NOT NULL,
    fee numeric(10,2) NOT NULL,
    insurance_estimate numeric(10,2) DEFAULT 0 NOT NULL,
    status character varying(20) DEFAULT 'Planned'::character varying NOT NULL,
    diagnosed_by character varying(200),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    billing_order character varying(10),
    phase_id integer,
    discount numeric(10,2),
    provider_id character varying(50),
    diagnosed_date date,
    start_date date,
    end_date date,
    is_archived boolean DEFAULT false NOT NULL,
    quadrant character varying(10),
    material_id integer,
    notes text,
    accepted_date date,
    scheduled_date date,
    duration_minutes integer,
    created_by integer,
    updated_by integer,
    referral_id integer,
    referral_type character varying(20),
    update_end_date_at_posting boolean DEFAULT false NOT NULL,
    re_estimate_at_posting boolean DEFAULT false NOT NULL,
    fee_schedule_id integer,
    counselor_user_id integer,
    status_before_scheduled character varying(20),
    fee_source character varying(24),
    fee_effective_date date,
    fee_override_reason character varying(255),
    coverage_pct numeric(5,2),
    coverage_rule_id integer,
    estimated_deductible numeric(10,2),
    sec_insurance_estimate numeric(10,2),
    ucr_fee numeric(10,2)
);


--
-- Name: treatment_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.treatment_plans (
    id character varying(50) NOT NULL,
    patient_id integer NOT NULL,
    office_id integer,
    legacy_id character varying(20),
    name character varying(200) NOT NULL,
    status character varying(20) DEFAULT 'Active'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    created_by integer
);


--
-- Name: user_group_memberships; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_group_memberships (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    user_id integer NOT NULL,
    group_id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: user_group_memberships_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_group_memberships_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_group_memberships_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_group_memberships_id_seq OWNED BY public.user_group_memberships.id;


--
-- Name: user_group_rights; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_group_rights (
    tenant_id integer NOT NULL,
    group_id integer NOT NULL,
    permission_id integer NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: user_group_rights_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_group_rights_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_group_rights_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_group_rights_id_seq OWNED BY public.user_group_rights.id;


--
-- Name: user_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_groups (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: user_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_groups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_groups_id_seq OWNED BY public.user_groups.id;


--
-- Name: user_ip_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_ip_rules (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    user_id integer NOT NULL,
    ip_address character varying(45) NOT NULL,
    rule_type character varying(10) DEFAULT 'allow'::character varying NOT NULL,
    description character varying(255),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: user_ip_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_ip_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_ip_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_ip_rules_id_seq OWNED BY public.user_ip_rules.id;


--
-- Name: user_login_restrictions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_login_restrictions (
    tenant_id integer NOT NULL,
    user_id integer NOT NULL,
    is_24_7 boolean NOT NULL,
    allowed_days character varying(50),
    start_time time without time zone,
    end_time time without time zone,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: user_login_restrictions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_login_restrictions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_login_restrictions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_login_restrictions_id_seq OWNED BY public.user_login_restrictions.id;


--
-- Name: user_offices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_offices (
    id integer NOT NULL,
    user_id integer NOT NULL,
    office_id integer NOT NULL,
    is_primary boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: user_offices_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_offices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_offices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_offices_id_seq OWNED BY public.user_offices.id;


--
-- Name: user_preferences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_preferences (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    user_id integer NOT NULL,
    pref_key character varying(100) NOT NULL,
    pref_value text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: user_preferences_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_preferences_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_preferences_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_preferences_id_seq OWNED BY public.user_preferences.id;


--
-- Name: user_presence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_presence (
    tenant_id integer NOT NULL,
    user_id integer NOT NULL,
    status character varying(20),
    last_seen_at timestamp without time zone,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: user_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_tasks (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    user_id integer NOT NULL,
    title character varying(255) NOT NULL,
    priority character varying(10) DEFAULT 'normal'::character varying NOT NULL,
    is_done boolean DEFAULT false NOT NULL,
    due_date date,
    notes text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: user_tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_tasks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_tasks_id_seq OWNED BY public.user_tasks.id;


--
-- Name: user_time_clock_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_time_clock_config (
    tenant_id integer NOT NULL,
    user_id integer NOT NULL,
    pay_rate numeric(10,2),
    overtime_method character varying(50),
    overtime_rate numeric(10,2),
    clock_in_required boolean NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    daily_threshold_hours numeric(5,2),
    weekly_threshold_hours numeric(5,2),
    week_start_day character varying(10)
);


--
-- Name: user_time_clock_config_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_time_clock_config_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_time_clock_config_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_time_clock_config_id_seq OWNED BY public.user_time_clock_config.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    legacy_id character varying(50),
    email character varying(255) NOT NULL,
    username character varying(50) NOT NULL,
    password_hash text NOT NULL,
    first_name character varying(100),
    last_name character varying(100),
    phone character varying(20),
    role character varying(50) DEFAULT 'staff'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    must_change_password boolean DEFAULT false NOT NULL,
    last_login_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    created_by integer,
    patient_access_level character varying(50),
    is_legacy_user boolean DEFAULT false NOT NULL,
    legacy_activation_completed boolean DEFAULT false NOT NULL,
    password_created_at timestamp without time zone,
    short_id character varying(6),
    report_access_provider_id character varying(50),
    custom_1 character varying(255),
    custom_2 character varying(255),
    signature_data text,
    image_url character varying(500),
    updated_by integer,
    signature_len integer,
    signature_device_source character varying(20),
    signature_updated_at timestamp without time zone,
    last_patient_id integer,
    signature_sig_string text,
    signature_sig_format character varying(24),
    signature_sig_compression smallint,
    signature_sig_encryption smallint,
    signature_point_count integer,
    signature_stroke_count integer,
    signature_device_vendor character varying(20),
    signature_device_model character varying(40),
    signature_device_serial character varying(40),
    signature_captured_user_agent character varying(255),
    signature_signed_at timestamp without time zone,
    current_office_id integer
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: utility_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.utility_runs (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    utility_id character varying(100) NOT NULL,
    office_id integer,
    run_by integer,
    status character varying(20) DEFAULT 'submitted'::character varying NOT NULL,
    parameters json,
    processed integer DEFAULT 0 NOT NULL,
    succeeded integer DEFAULT 0 NOT NULL,
    failed integer DEFAULT 0 NOT NULL,
    logs json,
    finished_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: utility_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.utility_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: utility_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.utility_runs_id_seq OWNED BY public.utility_runs.id;


--
-- Name: account_communications id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_communications ALTER COLUMN id SET DEFAULT nextval('public.account_communications_id_seq'::regclass);


--
-- Name: account_consents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_consents ALTER COLUMN id SET DEFAULT nextval('public.account_consents_id_seq'::regclass);


--
-- Name: account_holidays id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_holidays ALTER COLUMN id SET DEFAULT nextval('public.account_holidays_id_seq'::regclass);


--
-- Name: account_notes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_notes ALTER COLUMN id SET DEFAULT nextval('public.account_notes_id_seq'::regclass);


--
-- Name: account_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_settings ALTER COLUMN id SET DEFAULT nextval('public.account_settings_id_seq'::regclass);


--
-- Name: appointment_procedures id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointment_procedures ALTER COLUMN id SET DEFAULT nextval('public.appointment_procedures_id_seq'::regclass);


--
-- Name: appointnow_reasons id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointnow_reasons ALTER COLUMN id SET DEFAULT nextval('public.appointnow_reasons_id_seq'::regclass);


--
-- Name: audit_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs ALTER COLUMN id SET DEFAULT nextval('public.audit_logs_id_seq'::regclass);


--
-- Name: auth_action_tokens id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_action_tokens ALTER COLUMN id SET DEFAULT nextval('public.auth_action_tokens_id_seq'::regclass);


--
-- Name: campaigns id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns ALTER COLUMN id SET DEFAULT nextval('public.campaigns_id_seq'::regclass);


--
-- Name: caries_risk_assessments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.caries_risk_assessments ALTER COLUMN id SET DEFAULT nextval('public.caries_risk_assessments_id_seq'::regclass);


--
-- Name: chart_colors id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_colors ALTER COLUMN id SET DEFAULT nextval('public.chart_colors_id_seq'::regclass);


--
-- Name: chart_conditions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_conditions ALTER COLUMN id SET DEFAULT nextval('public.chart_conditions_id_seq'::regclass);


--
-- Name: chart_materials id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_materials ALTER COLUMN id SET DEFAULT nextval('public.chart_materials_id_seq'::regclass);


--
-- Name: chart_status_templates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_status_templates ALTER COLUMN id SET DEFAULT nextval('public.chart_status_templates_id_seq'::regclass);


--
-- Name: chart_tooth_notes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_tooth_notes ALTER COLUMN id SET DEFAULT nextval('public.chart_tooth_notes_id_seq'::regclass);


--
-- Name: claim_attachments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim_attachments ALTER COLUMN id SET DEFAULT nextval('public.claim_attachments_id_seq'::regclass);


--
-- Name: claim_submissions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim_submissions ALTER COLUMN id SET DEFAULT nextval('public.claim_submissions_id_seq'::regclass);


--
-- Name: code_bundle_items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_bundle_items ALTER COLUMN id SET DEFAULT nextval('public.code_bundle_items_id_seq'::regclass);


--
-- Name: code_bundles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_bundles ALTER COLUMN id SET DEFAULT nextval('public.code_bundles_id_seq'::regclass);


--
-- Name: codes_view id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.codes_view ALTER COLUMN id SET DEFAULT nextval('public.codes_view_id_seq'::regclass);


--
-- Name: collection_agencies id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_agencies ALTER COLUMN id SET DEFAULT nextval('public.collection_agencies_id_seq'::regclass);


--
-- Name: consent_signatures id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.consent_signatures ALTER COLUMN id SET DEFAULT nextval('public.consent_signatures_id_seq'::regclass);


--
-- Name: conversation_participants id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_participants ALTER COLUMN id SET DEFAULT nextval('public.conversation_participants_id_seq'::regclass);


--
-- Name: definition_groups id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.definition_groups ALTER COLUMN id SET DEFAULT nextval('public.definition_groups_id_seq'::regclass);


--
-- Name: definitions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.definitions ALTER COLUMN id SET DEFAULT nextval('public.definitions_id_seq'::regclass);


--
-- Name: dicom_instances id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_instances ALTER COLUMN id SET DEFAULT nextval('public.dicom_instances_id_seq'::regclass);


--
-- Name: dicom_series id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_series ALTER COLUMN id SET DEFAULT nextval('public.dicom_series_id_seq'::regclass);


--
-- Name: dicom_studies id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_studies ALTER COLUMN id SET DEFAULT nextval('public.dicom_studies_id_seq'::regclass);


--
-- Name: eligibility_checks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eligibility_checks ALTER COLUMN id SET DEFAULT nextval('public.eligibility_checks_id_seq'::regclass);


--
-- Name: email_messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_messages ALTER COLUMN id SET DEFAULT nextval('public.email_messages_id_seq'::regclass);


--
-- Name: employers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employers ALTER COLUMN id SET DEFAULT nextval('public.employers_id_seq'::regclass);


--
-- Name: explosion_code_items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.explosion_code_items ALTER COLUMN id SET DEFAULT nextval('public.explosion_code_items_id_seq'::regclass);


--
-- Name: explosion_codes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.explosion_codes ALTER COLUMN id SET DEFAULT nextval('public.explosion_codes_id_seq'::regclass);


--
-- Name: fee_schedule_assignments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_assignments ALTER COLUMN id SET DEFAULT nextval('public.fee_schedule_assignments_id_seq'::regclass);


--
-- Name: fee_schedule_entries id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_entries ALTER COLUMN id SET DEFAULT nextval('public.fee_schedule_entries_id_seq'::regclass);


--
-- Name: fee_schedules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedules ALTER COLUMN id SET DEFAULT nextval('public.fee_schedules_id_seq'::regclass);


--
-- Name: icd_codes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.icd_codes ALTER COLUMN id SET DEFAULT nextval('public.icd_codes_id_seq'::regclass);


--
-- Name: image_details id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_details ALTER COLUMN id SET DEFAULT nextval('public.image_details_id_seq'::regclass);


--
-- Name: image_groups id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_groups ALTER COLUMN id SET DEFAULT nextval('public.image_groups_id_seq'::regclass);


--
-- Name: imaging_templates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.imaging_templates ALTER COLUMN id SET DEFAULT nextval('public.imaging_templates_id_seq'::regclass);


--
-- Name: ins_custom_coverage id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ins_custom_coverage ALTER COLUMN id SET DEFAULT nextval('public.ins_custom_coverage_id_seq'::regclass);


--
-- Name: insurance_carriers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_carriers ALTER COLUMN id SET DEFAULT nextval('public.insurance_carriers_id_seq'::regclass);


--
-- Name: insurance_coverage_rules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_coverage_rules ALTER COLUMN id SET DEFAULT nextval('public.insurance_coverage_rules_id_seq'::regclass);


--
-- Name: insurance_plan_frequency_groups id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plan_frequency_groups ALTER COLUMN id SET DEFAULT nextval('public.insurance_plan_frequency_groups_id_seq'::regclass);


--
-- Name: insurance_plans id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plans ALTER COLUMN id SET DEFAULT nextval('public.insurance_plans_id_seq'::regclass);


--
-- Name: insurance_subscribers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_subscribers ALTER COLUMN id SET DEFAULT nextval('public.insurance_subscribers_id_seq'::regclass);


--
-- Name: labs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.labs ALTER COLUMN id SET DEFAULT nextval('public.labs_id_seq'::regclass);


--
-- Name: ledger_insurance_details id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ledger_insurance_details ALTER COLUMN id SET DEFAULT nextval('public.ledger_insurance_details_id_seq'::regclass);


--
-- Name: letter_batch_items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_batch_items ALTER COLUMN id SET DEFAULT nextval('public.letter_batch_items_id_seq'::regclass);


--
-- Name: letter_batch_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_batch_runs ALTER COLUMN id SET DEFAULT nextval('public.letter_batch_runs_id_seq'::regclass);


--
-- Name: letter_templates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_templates ALTER COLUMN id SET DEFAULT nextval('public.letter_templates_id_seq'::regclass);


--
-- Name: medical_history_details id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_history_details ALTER COLUMN id SET DEFAULT nextval('public.medical_history_details_id_seq'::regclass);


--
-- Name: medical_history_records id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_history_records ALTER COLUMN id SET DEFAULT nextval('public.medical_history_records_id_seq'::regclass);


--
-- Name: message_reactions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_reactions ALTER COLUMN id SET DEFAULT nextval('public.message_reactions_id_seq'::regclass);


--
-- Name: message_receipts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_receipts ALTER COLUMN id SET DEFAULT nextval('public.message_receipts_id_seq'::regclass);


--
-- Name: message_recipient_states id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_recipient_states ALTER COLUMN id SET DEFAULT nextval('public.message_recipient_states_id_seq'::regclass);


--
-- Name: mig_dicom_manifest id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mig_dicom_manifest ALTER COLUMN id SET DEFAULT nextval('public.mig_dicom_manifest_id_seq'::regclass);


--
-- Name: note_macros id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_macros ALTER COLUMN id SET DEFAULT nextval('public.note_macros_id_seq'::regclass);


--
-- Name: notifications id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications ALTER COLUMN id SET DEFAULT nextval('public.notifications_id_seq'::regclass);


--
-- Name: office_advanced_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_advanced_settings ALTER COLUMN id SET DEFAULT nextval('public.office_advanced_settings_id_seq'::regclass);


--
-- Name: office_code_bundles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_code_bundles ALTER COLUMN id SET DEFAULT nextval('public.office_code_bundles_id_seq'::regclass);


--
-- Name: office_groups id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_groups ALTER COLUMN id SET DEFAULT nextval('public.office_groups_id_seq'::regclass);


--
-- Name: office_integrations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_integrations ALTER COLUMN id SET DEFAULT nextval('public.office_integrations_id_seq'::regclass);


--
-- Name: office_letter_templates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_letter_templates ALTER COLUMN id SET DEFAULT nextval('public.office_letter_templates_id_seq'::regclass);


--
-- Name: office_note_macros id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_note_macros ALTER COLUMN id SET DEFAULT nextval('public.office_note_macros_id_seq'::regclass);


--
-- Name: office_phone_assignments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_phone_assignments ALTER COLUMN id SET DEFAULT nextval('public.office_phone_assignments_id_seq'::regclass);


--
-- Name: office_prescription_library id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_prescription_library ALTER COLUMN id SET DEFAULT nextval('public.office_prescription_library_id_seq'::regclass);


--
-- Name: office_procedure_codes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_procedure_codes ALTER COLUMN id SET DEFAULT nextval('public.office_procedure_codes_id_seq'::regclass);


--
-- Name: office_production_types id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_production_types ALTER COLUMN id SET DEFAULT nextval('public.office_production_types_id_seq'::regclass);


--
-- Name: office_schedule_days id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_schedule_days ALTER COLUMN id SET DEFAULT nextval('public.office_schedule_days_id_seq'::regclass);


--
-- Name: office_smart_assist id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_smart_assist ALTER COLUMN id SET DEFAULT nextval('public.office_smart_assist_id_seq'::regclass);


--
-- Name: office_smart_assist_items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_smart_assist_items ALTER COLUMN id SET DEFAULT nextval('public.office_smart_assist_items_id_seq'::regclass);


--
-- Name: office_statement_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_statement_settings ALTER COLUMN id SET DEFAULT nextval('public.office_statement_settings_id_seq'::regclass);


--
-- Name: offices id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offices ALTER COLUMN id SET DEFAULT nextval('public.offices_id_seq'::regclass);


--
-- Name: ortho_plans id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ortho_plans ALTER COLUMN id SET DEFAULT nextval('public.ortho_plans_id_seq'::regclass);


--
-- Name: patient_adjustments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_adjustments ALTER COLUMN id SET DEFAULT nextval('public.patient_adjustments_id_seq'::regclass);


--
-- Name: patient_alerts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_alerts ALTER COLUMN id SET DEFAULT nextval('public.patient_alerts_id_seq'::regclass);


--
-- Name: patient_consents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_consents ALTER COLUMN id SET DEFAULT nextval('public.patient_consents_id_seq'::regclass);


--
-- Name: patient_documents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_documents ALTER COLUMN id SET DEFAULT nextval('public.patient_documents_id_seq'::regclass);


--
-- Name: patient_emergency_contacts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_emergency_contacts ALTER COLUMN id SET DEFAULT nextval('public.patient_emergency_contacts_id_seq'::regclass);


--
-- Name: patient_ins_payment_plans id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_ins_payment_plans ALTER COLUMN id SET DEFAULT nextval('public.patient_ins_payment_plans_id_seq'::regclass);


--
-- Name: patient_insurance id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_insurance ALTER COLUMN id SET DEFAULT nextval('public.patient_insurance_id_seq'::regclass);


--
-- Name: patient_medical_alerts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_alerts ALTER COLUMN id SET DEFAULT nextval('public.patient_medical_alerts_id_seq'::regclass);


--
-- Name: patient_medical_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history ALTER COLUMN id SET DEFAULT nextval('public.patient_medical_history_id_seq'::regclass);


--
-- Name: patient_medical_history_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history_events ALTER COLUMN id SET DEFAULT nextval('public.patient_medical_history_events_id_seq'::regclass);


--
-- Name: patient_notes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_notes ALTER COLUMN id SET DEFAULT nextval('public.patient_notes_id_seq'::regclass);


--
-- Name: patient_opening_balances id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_opening_balances ALTER COLUMN id SET DEFAULT nextval('public.patient_opening_balances_id_seq'::regclass);


--
-- Name: patient_payment_plans id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payment_plans ALTER COLUMN id SET DEFAULT nextval('public.patient_payment_plans_id_seq'::regclass);


--
-- Name: patient_plan_installments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_plan_installments ALTER COLUMN id SET DEFAULT nextval('public.patient_plan_installments_id_seq'::regclass);


--
-- Name: patient_questionnaire_responses id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_questionnaire_responses ALTER COLUMN id SET DEFAULT nextval('public.patient_questionnaire_responses_id_seq'::regclass);


--
-- Name: patient_recalls id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_recalls ALTER COLUMN id SET DEFAULT nextval('public.patient_recalls_id_seq'::regclass);


--
-- Name: patient_refunds id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_refunds ALTER COLUMN id SET DEFAULT nextval('public.patient_refunds_id_seq'::regclass);


--
-- Name: patient_reg_plans id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_reg_plans ALTER COLUMN id SET DEFAULT nextval('public.patient_reg_plans_id_seq'::regclass);


--
-- Name: patient_sec_ins_payment_plans id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_sec_ins_payment_plans ALTER COLUMN id SET DEFAULT nextval('public.patient_sec_ins_payment_plans_id_seq'::regclass);


--
-- Name: patient_signatures id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_signatures ALTER COLUMN id SET DEFAULT nextval('public.patient_signatures_id_seq'::regclass);


--
-- Name: patient_statements id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_statements ALTER COLUMN id SET DEFAULT nextval('public.patient_statements_id_seq'::regclass);


--
-- Name: patients id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients ALTER COLUMN id SET DEFAULT nextval('public.patients_id_seq'::regclass);


--
-- Name: payment_allocations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_allocations ALTER COLUMN id SET DEFAULT nextval('public.payment_allocations_id_seq'::regclass);


--
-- Name: perio_chart_activity id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_chart_activity ALTER COLUMN id SET DEFAULT nextval('public.perio_chart_activity_id_seq'::regclass);


--
-- Name: perio_chart_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_chart_settings ALTER COLUMN id SET DEFAULT nextval('public.perio_chart_settings_id_seq'::regclass);


--
-- Name: perio_chart_templates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_chart_templates ALTER COLUMN id SET DEFAULT nextval('public.perio_chart_templates_id_seq'::regclass);


--
-- Name: perio_exam_details id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_exam_details ALTER COLUMN id SET DEFAULT nextval('public.perio_exam_details_id_seq'::regclass);


--
-- Name: perio_exams id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_exams ALTER COLUMN id SET DEFAULT nextval('public.perio_exams_id_seq'::regclass);


--
-- Name: permissions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permissions ALTER COLUMN id SET DEFAULT nextval('public.permissions_id_seq'::regclass);


--
-- Name: place_of_service_codes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.place_of_service_codes ALTER COLUMN id SET DEFAULT nextval('public.place_of_service_codes_id_seq'::regclass);


--
-- Name: postcard_templates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.postcard_templates ALTER COLUMN id SET DEFAULT nextval('public.postcard_templates_id_seq'::regclass);


--
-- Name: prescription_library id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescription_library ALTER COLUMN id SET DEFAULT nextval('public.prescription_library_id_seq'::regclass);


--
-- Name: prescriptions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescriptions ALTER COLUMN id SET DEFAULT nextval('public.prescriptions_id_seq'::regclass);


--
-- Name: procedure_fee_provenance id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_fee_provenance ALTER COLUMN id SET DEFAULT nextval('public.procedure_fee_provenance_id_seq'::regclass);


--
-- Name: procedure_insurance_rules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_insurance_rules ALTER COLUMN id SET DEFAULT nextval('public.procedure_insurance_rules_id_seq'::regclass);


--
-- Name: production_types id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.production_types ALTER COLUMN id SET DEFAULT nextval('public.production_types_id_seq'::regclass);


--
-- Name: progress_note_attachments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.progress_note_attachments ALTER COLUMN id SET DEFAULT nextval('public.progress_note_attachments_id_seq'::regclass);


--
-- Name: progress_notes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.progress_notes ALTER COLUMN id SET DEFAULT nextval('public.progress_notes_id_seq'::regclass);


--
-- Name: provider_carrier_logins id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_carrier_logins ALTER COLUMN id SET DEFAULT nextval('public.provider_carrier_logins_id_seq'::regclass);


--
-- Name: provider_holidays id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_holidays ALTER COLUMN id SET DEFAULT nextval('public.provider_holidays_id_seq'::regclass);


--
-- Name: provider_insurance_ids id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_insurance_ids ALTER COLUMN id SET DEFAULT nextval('public.provider_insurance_ids_id_seq'::regclass);


--
-- Name: provider_offices id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_offices ALTER COLUMN id SET DEFAULT nextval('public.provider_offices_id_seq'::regclass);


--
-- Name: provider_procedure_codes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_procedure_codes ALTER COLUMN id SET DEFAULT nextval('public.provider_procedure_codes_id_seq'::regclass);


--
-- Name: provider_referral_offices id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_referral_offices ALTER COLUMN id SET DEFAULT nextval('public.provider_referral_offices_id_seq'::regclass);


--
-- Name: provider_route_slips id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_route_slips ALTER COLUMN id SET DEFAULT nextval('public.provider_route_slips_id_seq'::regclass);


--
-- Name: provider_schedule_days id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_schedule_days ALTER COLUMN id SET DEFAULT nextval('public.provider_schedule_days_id_seq'::regclass);


--
-- Name: provider_signatures id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_signatures ALTER COLUMN id SET DEFAULT nextval('public.provider_signatures_id_seq'::regclass);


--
-- Name: provider_watermarks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_watermarks ALTER COLUMN id SET DEFAULT nextval('public.provider_watermarks_id_seq'::regclass);


--
-- Name: questionnaire_headers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.questionnaire_headers ALTER COLUMN id SET DEFAULT nextval('public.questionnaire_headers_id_seq'::regclass);


--
-- Name: questionnaire_options id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.questionnaire_options ALTER COLUMN id SET DEFAULT nextval('public.questionnaire_options_id_seq'::regclass);


--
-- Name: referral_demog_details id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_demog_details ALTER COLUMN id SET DEFAULT nextval('public.referral_demog_details_id_seq'::regclass);


--
-- Name: referral_demog_headers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_demog_headers ALTER COLUMN id SET DEFAULT nextval('public.referral_demog_headers_id_seq'::regclass);


--
-- Name: referrals id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referrals ALTER COLUMN id SET DEFAULT nextval('public.referrals_id_seq'::regclass);


--
-- Name: refresh_tokens id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens ALTER COLUMN id SET DEFAULT nextval('public.refresh_tokens_id_seq'::regclass);


--
-- Name: responsible_parties id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.responsible_parties ALTER COLUMN id SET DEFAULT nextval('public.responsible_parties_id_seq'::regclass);


--
-- Name: ringcentral_sms_subscriptions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ringcentral_sms_subscriptions ALTER COLUMN id SET DEFAULT nextval('public.ringcentral_sms_subscriptions_id_seq'::regclass);


--
-- Name: signature_audit_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signature_audit_events ALTER COLUMN id SET DEFAULT nextval('public.signature_audit_events_id_seq'::regclass);


--
-- Name: sms_messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_messages ALTER COLUMN id SET DEFAULT nextval('public.sms_messages_id_seq'::regclass);


--
-- Name: sms_templates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_templates ALTER COLUMN id SET DEFAULT nextval('public.sms_templates_id_seq'::regclass);


--
-- Name: stored_objects id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stored_objects ALTER COLUMN id SET DEFAULT nextval('public.stored_objects_id_seq'::regclass);


--
-- Name: support_tickets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_tickets ALTER COLUMN id SET DEFAULT nextval('public.support_tickets_id_seq'::regclass);


--
-- Name: tenants id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants ALTER COLUMN id SET DEFAULT nextval('public.tenants_id_seq'::regclass);


--
-- Name: time_clock_entries id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_entries ALTER COLUMN id SET DEFAULT nextval('public.time_clock_entries_id_seq'::regclass);


--
-- Name: time_clock_entry_edits id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_entry_edits ALTER COLUMN id SET DEFAULT nextval('public.time_clock_entry_edits_id_seq'::regclass);


--
-- Name: time_clock_periods id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_periods ALTER COLUMN id SET DEFAULT nextval('public.time_clock_periods_id_seq'::regclass);


--
-- Name: time_clock_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_settings ALTER COLUMN id SET DEFAULT nextval('public.time_clock_settings_id_seq'::regclass);


--
-- Name: treatment_plan_insurance_details id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_insurance_details ALTER COLUMN id SET DEFAULT nextval('public.treatment_plan_insurance_details_id_seq'::regclass);


--
-- Name: treatment_plan_item_icd_codes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_item_icd_codes ALTER COLUMN id SET DEFAULT nextval('public.treatment_plan_item_icd_codes_id_seq'::regclass);


--
-- Name: user_group_memberships id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_memberships ALTER COLUMN id SET DEFAULT nextval('public.user_group_memberships_id_seq'::regclass);


--
-- Name: user_group_rights id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_rights ALTER COLUMN id SET DEFAULT nextval('public.user_group_rights_id_seq'::regclass);


--
-- Name: user_groups id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_groups ALTER COLUMN id SET DEFAULT nextval('public.user_groups_id_seq'::regclass);


--
-- Name: user_ip_rules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_ip_rules ALTER COLUMN id SET DEFAULT nextval('public.user_ip_rules_id_seq'::regclass);


--
-- Name: user_login_restrictions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_login_restrictions ALTER COLUMN id SET DEFAULT nextval('public.user_login_restrictions_id_seq'::regclass);


--
-- Name: user_offices id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_offices ALTER COLUMN id SET DEFAULT nextval('public.user_offices_id_seq'::regclass);


--
-- Name: user_preferences id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_preferences ALTER COLUMN id SET DEFAULT nextval('public.user_preferences_id_seq'::regclass);


--
-- Name: user_tasks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_tasks ALTER COLUMN id SET DEFAULT nextval('public.user_tasks_id_seq'::regclass);


--
-- Name: user_time_clock_config id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_time_clock_config ALTER COLUMN id SET DEFAULT nextval('public.user_time_clock_config_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: utility_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.utility_runs ALTER COLUMN id SET DEFAULT nextval('public.utility_runs_id_seq'::regclass);


--
-- Name: account_notes account_notes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_notes
    ADD CONSTRAINT account_notes_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: appointment_procedures appointment_procedures_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointment_procedures
    ADD CONSTRAINT appointment_procedures_pkey PRIMARY KEY (id);


--
-- Name: appointments appointments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT appointments_pkey PRIMARY KEY (id);


--
-- Name: caries_risk_assessments caries_risk_assessments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.caries_risk_assessments
    ADD CONSTRAINT caries_risk_assessments_pkey PRIMARY KEY (id);


--
-- Name: chart_colors chart_colors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_colors
    ADD CONSTRAINT chart_colors_pkey PRIMARY KEY (id);


--
-- Name: chart_conditions chart_conditions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_conditions
    ADD CONSTRAINT chart_conditions_pkey PRIMARY KEY (id);


--
-- Name: chart_materials chart_materials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_materials
    ADD CONSTRAINT chart_materials_pkey PRIMARY KEY (id);


--
-- Name: claim_submissions claim_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim_submissions
    ADD CONSTRAINT claim_submissions_pkey PRIMARY KEY (id);


--
-- Name: code_bundle_items code_bundle_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_bundle_items
    ADD CONSTRAINT code_bundle_items_pkey PRIMARY KEY (id);


--
-- Name: code_bundles code_bundles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_bundles
    ADD CONSTRAINT code_bundles_pkey PRIMARY KEY (id);


--
-- Name: codes_view codes_view_office_id_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.codes_view
    ADD CONSTRAINT codes_view_office_id_code_key UNIQUE (office_id, code);


--
-- Name: codes_view codes_view_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.codes_view
    ADD CONSTRAINT codes_view_pkey PRIMARY KEY (id);


--
-- Name: collection_agencies collection_agencies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_agencies
    ADD CONSTRAINT collection_agencies_pkey PRIMARY KEY (id);


--
-- Name: definition_groups definition_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.definition_groups
    ADD CONSTRAINT definition_groups_pkey PRIMARY KEY (id);


--
-- Name: definition_groups definition_groups_tenant_id_group_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.definition_groups
    ADD CONSTRAINT definition_groups_tenant_id_group_code_key UNIQUE (tenant_id, group_code);


--
-- Name: definitions definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.definitions
    ADD CONSTRAINT definitions_pkey PRIMARY KEY (id);


--
-- Name: eligibility_checks eligibility_checks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eligibility_checks
    ADD CONSTRAINT eligibility_checks_pkey PRIMARY KEY (id);


--
-- Name: employers employers_legacy_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employers
    ADD CONSTRAINT employers_legacy_id_key UNIQUE (legacy_id);


--
-- Name: employers employers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employers
    ADD CONSTRAINT employers_pkey PRIMARY KEY (id);


--
-- Name: fee_schedule_assignments fee_schedule_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_assignments
    ADD CONSTRAINT fee_schedule_assignments_pkey PRIMARY KEY (id);


--
-- Name: fee_schedule_entries fee_schedule_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_entries
    ADD CONSTRAINT fee_schedule_entries_pkey PRIMARY KEY (id);


--
-- Name: fee_schedules fee_schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedules
    ADD CONSTRAINT fee_schedules_pkey PRIMARY KEY (id);


--
-- Name: image_details image_details_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_details
    ADD CONSTRAINT image_details_pkey PRIMARY KEY (id);


--
-- Name: image_groups image_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_groups
    ADD CONSTRAINT image_groups_pkey PRIMARY KEY (id);


--
-- Name: imaging_templates imaging_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.imaging_templates
    ADD CONSTRAINT imaging_templates_pkey PRIMARY KEY (id);


--
-- Name: ins_custom_coverage ins_custom_coverage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ins_custom_coverage
    ADD CONSTRAINT ins_custom_coverage_pkey PRIMARY KEY (id);


--
-- Name: insurance_carriers insurance_carriers_legacy_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_carriers
    ADD CONSTRAINT insurance_carriers_legacy_id_key UNIQUE (legacy_id);


--
-- Name: insurance_carriers insurance_carriers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_carriers
    ADD CONSTRAINT insurance_carriers_pkey PRIMARY KEY (id);


--
-- Name: insurance_claims insurance_claims_claim_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_claims
    ADD CONSTRAINT insurance_claims_claim_number_key UNIQUE (claim_number);


--
-- Name: insurance_claims insurance_claims_legacy_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_claims
    ADD CONSTRAINT insurance_claims_legacy_id_key UNIQUE (legacy_id);


--
-- Name: insurance_claims insurance_claims_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_claims
    ADD CONSTRAINT insurance_claims_pkey PRIMARY KEY (id);


--
-- Name: insurance_coverage_rules insurance_coverage_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_coverage_rules
    ADD CONSTRAINT insurance_coverage_rules_pkey PRIMARY KEY (id);


--
-- Name: insurance_plans insurance_plans_legacy_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plans
    ADD CONSTRAINT insurance_plans_legacy_id_key UNIQUE (legacy_id);


--
-- Name: insurance_plans insurance_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plans
    ADD CONSTRAINT insurance_plans_pkey PRIMARY KEY (id);


--
-- Name: insurance_subscribers insurance_subscribers_legacy_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_subscribers
    ADD CONSTRAINT insurance_subscribers_legacy_id_key UNIQUE (legacy_id);


--
-- Name: insurance_subscribers insurance_subscribers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_subscribers
    ADD CONSTRAINT insurance_subscribers_pkey PRIMARY KEY (id);


--
-- Name: ledger_insurance_details ledger_insurance_details_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ledger_insurance_details
    ADD CONSTRAINT ledger_insurance_details_pkey PRIMARY KEY (id);


--
-- Name: letter_templates letter_templates_legacy_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_templates
    ADD CONSTRAINT letter_templates_legacy_id_key UNIQUE (legacy_id);


--
-- Name: letter_templates letter_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_templates
    ADD CONSTRAINT letter_templates_pkey PRIMARY KEY (id);


--
-- Name: medical_history_details medical_history_details_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_history_details
    ADD CONSTRAINT medical_history_details_pkey PRIMARY KEY (id);


--
-- Name: medical_history_records medical_history_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_history_records
    ADD CONSTRAINT medical_history_records_pkey PRIMARY KEY (id);


--
-- Name: mig_dicom_manifest mig_dicom_manifest_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mig_dicom_manifest
    ADD CONSTRAINT mig_dicom_manifest_pkey PRIMARY KEY (id);


--
-- Name: mig_dicom_manifest mig_dicom_manifest_source_path_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mig_dicom_manifest
    ADD CONSTRAINT mig_dicom_manifest_source_path_key UNIQUE (source_path);


--
-- Name: mig_dicom_object mig_dicom_object_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mig_dicom_object
    ADD CONSTRAINT mig_dicom_object_pkey PRIMARY KEY (content_sha256);


--
-- Name: mig_patient_link mig_patient_link_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mig_patient_link
    ADD CONSTRAINT mig_patient_link_pkey PRIMARY KEY (patient_id_raw);


--
-- Name: note_macros note_macros_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_macros
    ADD CONSTRAINT note_macros_pkey PRIMARY KEY (id);


--
-- Name: office_groups office_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_groups
    ADD CONSTRAINT office_groups_pkey PRIMARY KEY (id);


--
-- Name: offices offices_legacy_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offices
    ADD CONSTRAINT offices_legacy_id_key UNIQUE (legacy_id);


--
-- Name: offices offices_office_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offices
    ADD CONSTRAINT offices_office_code_key UNIQUE (office_code);


--
-- Name: offices offices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offices
    ADD CONSTRAINT offices_pkey PRIMARY KEY (id);


--
-- Name: operatories operatories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.operatories
    ADD CONSTRAINT operatories_pkey PRIMARY KEY (id);


--
-- Name: ortho_plans ortho_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ortho_plans
    ADD CONSTRAINT ortho_plans_pkey PRIMARY KEY (id);


--
-- Name: patient_alerts patient_alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_alerts
    ADD CONSTRAINT patient_alerts_pkey PRIMARY KEY (id);


--
-- Name: patient_ins_payment_plans patient_ins_payment_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_ins_payment_plans
    ADD CONSTRAINT patient_ins_payment_plans_pkey PRIMARY KEY (id);


--
-- Name: patient_insurance patient_insurance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_insurance
    ADD CONSTRAINT patient_insurance_pkey PRIMARY KEY (id);


--
-- Name: patient_notes patient_notes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_notes
    ADD CONSTRAINT patient_notes_pkey PRIMARY KEY (id);


--
-- Name: patient_payment_plans patient_payment_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payment_plans
    ADD CONSTRAINT patient_payment_plans_pkey PRIMARY KEY (id);


--
-- Name: patient_payments patient_payments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payments
    ADD CONSTRAINT patient_payments_pkey PRIMARY KEY (id);


--
-- Name: patient_procedures patient_procedures_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT patient_procedures_pkey PRIMARY KEY (id);


--
-- Name: patient_recalls patient_recalls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_recalls
    ADD CONSTRAINT patient_recalls_pkey PRIMARY KEY (id);


--
-- Name: patient_reg_plans patient_reg_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_reg_plans
    ADD CONSTRAINT patient_reg_plans_pkey PRIMARY KEY (id);


--
-- Name: patient_sec_ins_payment_plans patient_sec_ins_payment_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_sec_ins_payment_plans
    ADD CONSTRAINT patient_sec_ins_payment_plans_pkey PRIMARY KEY (id);


--
-- Name: patient_signatures patient_signatures_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_signatures
    ADD CONSTRAINT patient_signatures_pkey PRIMARY KEY (id);


--
-- Name: patients patients_legacy_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT patients_legacy_id_key UNIQUE (legacy_id);


--
-- Name: patients patients_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT patients_pkey PRIMARY KEY (id);


--
-- Name: payment_allocations payment_allocations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_allocations
    ADD CONSTRAINT payment_allocations_pkey PRIMARY KEY (id);


--
-- Name: perio_chart_activity perio_chart_activity_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_chart_activity
    ADD CONSTRAINT perio_chart_activity_pkey PRIMARY KEY (id);


--
-- Name: perio_chart_settings perio_chart_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_chart_settings
    ADD CONSTRAINT perio_chart_settings_pkey PRIMARY KEY (id);


--
-- Name: perio_chart_settings perio_chart_settings_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_chart_settings
    ADD CONSTRAINT perio_chart_settings_user_id_key UNIQUE (user_id);


--
-- Name: perio_exam_details perio_exam_details_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_exam_details
    ADD CONSTRAINT perio_exam_details_pkey PRIMARY KEY (id);


--
-- Name: perio_exams perio_exams_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_exams
    ADD CONSTRAINT perio_exams_pkey PRIMARY KEY (id);


--
-- Name: account_communications pk_account_communications; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_communications
    ADD CONSTRAINT pk_account_communications PRIMARY KEY (id);


--
-- Name: account_consents pk_account_consents; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_consents
    ADD CONSTRAINT pk_account_consents PRIMARY KEY (id);


--
-- Name: account_holidays pk_account_holidays; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_holidays
    ADD CONSTRAINT pk_account_holidays PRIMARY KEY (id);


--
-- Name: account_settings pk_account_settings; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_settings
    ADD CONSTRAINT pk_account_settings PRIMARY KEY (id);


--
-- Name: appointnow_reasons pk_appointnow_reasons; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointnow_reasons
    ADD CONSTRAINT pk_appointnow_reasons PRIMARY KEY (id);


--
-- Name: audit_logs pk_audit_logs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT pk_audit_logs PRIMARY KEY (id);


--
-- Name: auth_action_tokens pk_auth_action_tokens; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_action_tokens
    ADD CONSTRAINT pk_auth_action_tokens PRIMARY KEY (id);


--
-- Name: booking_acknowledgement_texts pk_booking_acknowledgement_texts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_acknowledgement_texts
    ADD CONSTRAINT pk_booking_acknowledgement_texts PRIMARY KEY (text_hash);


--
-- Name: booking_requests pk_booking_requests; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests
    ADD CONSTRAINT pk_booking_requests PRIMARY KEY (id);


--
-- Name: campaigns pk_campaigns; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT pk_campaigns PRIMARY KEY (id);


--
-- Name: chart_settings pk_chart_settings; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_settings
    ADD CONSTRAINT pk_chart_settings PRIMARY KEY (patient_id);


--
-- Name: chart_status_templates pk_chart_status_templates; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_status_templates
    ADD CONSTRAINT pk_chart_status_templates PRIMARY KEY (id);


--
-- Name: chart_tooth_notes pk_chart_tooth_notes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_tooth_notes
    ADD CONSTRAINT pk_chart_tooth_notes PRIMARY KEY (id);


--
-- Name: claim_attachments pk_claim_attachments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim_attachments
    ADD CONSTRAINT pk_claim_attachments PRIMARY KEY (id);


--
-- Name: consent_signatures pk_consent_signatures; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.consent_signatures
    ADD CONSTRAINT pk_consent_signatures PRIMARY KEY (id);


--
-- Name: conversation_participants pk_conversation_participants; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_participants
    ADD CONSTRAINT pk_conversation_participants PRIMARY KEY (id);


--
-- Name: conversations pk_conversations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT pk_conversations PRIMARY KEY (id);


--
-- Name: dicom_instances pk_dicom_instances; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_instances
    ADD CONSTRAINT pk_dicom_instances PRIMARY KEY (id);


--
-- Name: dicom_series pk_dicom_series; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_series
    ADD CONSTRAINT pk_dicom_series PRIMARY KEY (id);


--
-- Name: dicom_studies pk_dicom_studies; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_studies
    ADD CONSTRAINT pk_dicom_studies PRIMARY KEY (id);


--
-- Name: email_messages pk_email_messages; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_messages
    ADD CONSTRAINT pk_email_messages PRIMARY KEY (id);


--
-- Name: explosion_code_items pk_explosion_code_items; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.explosion_code_items
    ADD CONSTRAINT pk_explosion_code_items PRIMARY KEY (id);


--
-- Name: explosion_codes pk_explosion_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.explosion_codes
    ADD CONSTRAINT pk_explosion_codes PRIMARY KEY (id);


--
-- Name: icd_codes pk_icd_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.icd_codes
    ADD CONSTRAINT pk_icd_codes PRIMARY KEY (id);


--
-- Name: insurance_plan_frequency_groups pk_insurance_plan_frequency_groups; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plan_frequency_groups
    ADD CONSTRAINT pk_insurance_plan_frequency_groups PRIMARY KEY (id);


--
-- Name: labs pk_labs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.labs
    ADD CONSTRAINT pk_labs PRIMARY KEY (id);


--
-- Name: letter_batch_items pk_letter_batch_items; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_batch_items
    ADD CONSTRAINT pk_letter_batch_items PRIMARY KEY (id);


--
-- Name: letter_batch_runs pk_letter_batch_runs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_batch_runs
    ADD CONSTRAINT pk_letter_batch_runs PRIMARY KEY (id);


--
-- Name: message_attachments pk_message_attachments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_attachments
    ADD CONSTRAINT pk_message_attachments PRIMARY KEY (id);


--
-- Name: message_reactions pk_message_reactions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_reactions
    ADD CONSTRAINT pk_message_reactions PRIMARY KEY (id);


--
-- Name: message_receipts pk_message_receipts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_receipts
    ADD CONSTRAINT pk_message_receipts PRIMARY KEY (id);


--
-- Name: message_recipient_states pk_message_recipient_states; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_recipient_states
    ADD CONSTRAINT pk_message_recipient_states PRIMARY KEY (id);


--
-- Name: messages pk_messages; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT pk_messages PRIMARY KEY (id);


--
-- Name: notifications pk_notifications; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT pk_notifications PRIMARY KEY (id);


--
-- Name: office_advanced_settings pk_office_advanced_settings; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_advanced_settings
    ADD CONSTRAINT pk_office_advanced_settings PRIMARY KEY (id);


--
-- Name: office_code_bundles pk_office_code_bundles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_code_bundles
    ADD CONSTRAINT pk_office_code_bundles PRIMARY KEY (id);


--
-- Name: office_integrations pk_office_integrations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_integrations
    ADD CONSTRAINT pk_office_integrations PRIMARY KEY (id);


--
-- Name: office_letter_templates pk_office_letter_templates; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_letter_templates
    ADD CONSTRAINT pk_office_letter_templates PRIMARY KEY (id);


--
-- Name: office_note_macros pk_office_note_macros; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_note_macros
    ADD CONSTRAINT pk_office_note_macros PRIMARY KEY (id);


--
-- Name: office_phone_assignments pk_office_phone_assignments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_phone_assignments
    ADD CONSTRAINT pk_office_phone_assignments PRIMARY KEY (id);


--
-- Name: office_prescription_library pk_office_prescription_library; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_prescription_library
    ADD CONSTRAINT pk_office_prescription_library PRIMARY KEY (id);


--
-- Name: office_procedure_codes pk_office_procedure_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_procedure_codes
    ADD CONSTRAINT pk_office_procedure_codes PRIMARY KEY (id);


--
-- Name: office_production_types pk_office_production_types; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_production_types
    ADD CONSTRAINT pk_office_production_types PRIMARY KEY (id);


--
-- Name: office_schedule_days pk_office_schedule_days; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_schedule_days
    ADD CONSTRAINT pk_office_schedule_days PRIMARY KEY (id);


--
-- Name: office_smart_assist pk_office_smart_assist; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_smart_assist
    ADD CONSTRAINT pk_office_smart_assist PRIMARY KEY (id);


--
-- Name: office_smart_assist_items pk_office_smart_assist_items; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_smart_assist_items
    ADD CONSTRAINT pk_office_smart_assist_items PRIMARY KEY (id);


--
-- Name: office_statement_settings pk_office_statement_settings; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_statement_settings
    ADD CONSTRAINT pk_office_statement_settings PRIMARY KEY (id);


--
-- Name: patient_adjustments pk_patient_adjustments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_adjustments
    ADD CONSTRAINT pk_patient_adjustments PRIMARY KEY (id);


--
-- Name: patient_consents pk_patient_consents; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_consents
    ADD CONSTRAINT pk_patient_consents PRIMARY KEY (id);


--
-- Name: patient_documents pk_patient_documents; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_documents
    ADD CONSTRAINT pk_patient_documents PRIMARY KEY (id);


--
-- Name: patient_emergency_contacts pk_patient_emergency_contacts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_emergency_contacts
    ADD CONSTRAINT pk_patient_emergency_contacts PRIMARY KEY (id);


--
-- Name: patient_medical_alerts pk_patient_medical_alerts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_alerts
    ADD CONSTRAINT pk_patient_medical_alerts PRIMARY KEY (id);


--
-- Name: patient_medical_history pk_patient_medical_history; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history
    ADD CONSTRAINT pk_patient_medical_history PRIMARY KEY (id);


--
-- Name: patient_medical_history_events pk_patient_medical_history_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history_events
    ADD CONSTRAINT pk_patient_medical_history_events PRIMARY KEY (id);


--
-- Name: patient_opening_balances pk_patient_opening_balances; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_opening_balances
    ADD CONSTRAINT pk_patient_opening_balances PRIMARY KEY (id);


--
-- Name: patient_plan_installments pk_patient_plan_installments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_plan_installments
    ADD CONSTRAINT pk_patient_plan_installments PRIMARY KEY (id);


--
-- Name: patient_questionnaire_responses pk_patient_questionnaire_responses; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_questionnaire_responses
    ADD CONSTRAINT pk_patient_questionnaire_responses PRIMARY KEY (id);


--
-- Name: patient_refunds pk_patient_refunds; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_refunds
    ADD CONSTRAINT pk_patient_refunds PRIMARY KEY (id);


--
-- Name: patient_statements pk_patient_statements; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_statements
    ADD CONSTRAINT pk_patient_statements PRIMARY KEY (id);


--
-- Name: perio_chart_templates pk_perio_chart_templates; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_chart_templates
    ADD CONSTRAINT pk_perio_chart_templates PRIMARY KEY (id);


--
-- Name: permissions pk_permissions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT pk_permissions PRIMARY KEY (id);


--
-- Name: place_of_service_codes pk_place_of_service_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.place_of_service_codes
    ADD CONSTRAINT pk_place_of_service_codes PRIMARY KEY (id);


--
-- Name: procedure_fee_provenance pk_procedure_fee_provenance; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_fee_provenance
    ADD CONSTRAINT pk_procedure_fee_provenance PRIMARY KEY (id);


--
-- Name: procedure_insurance_rules pk_procedure_insurance_rules; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_insurance_rules
    ADD CONSTRAINT pk_procedure_insurance_rules PRIMARY KEY (id);


--
-- Name: production_types pk_production_types; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.production_types
    ADD CONSTRAINT pk_production_types PRIMARY KEY (id);


--
-- Name: progress_note_attachments pk_progress_note_attachments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.progress_note_attachments
    ADD CONSTRAINT pk_progress_note_attachments PRIMARY KEY (id);


--
-- Name: provider_carrier_logins pk_provider_carrier_logins; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_carrier_logins
    ADD CONSTRAINT pk_provider_carrier_logins PRIMARY KEY (id);


--
-- Name: provider_holidays pk_provider_holidays; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_holidays
    ADD CONSTRAINT pk_provider_holidays PRIMARY KEY (id);


--
-- Name: provider_offices pk_provider_offices; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_offices
    ADD CONSTRAINT pk_provider_offices PRIMARY KEY (id);


--
-- Name: provider_procedure_codes pk_provider_procedure_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_procedure_codes
    ADD CONSTRAINT pk_provider_procedure_codes PRIMARY KEY (id);


--
-- Name: provider_referral_offices pk_provider_referral_offices; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_referral_offices
    ADD CONSTRAINT pk_provider_referral_offices PRIMARY KEY (id);


--
-- Name: provider_schedule_days pk_provider_schedule_days; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_schedule_days
    ADD CONSTRAINT pk_provider_schedule_days PRIMARY KEY (id);


--
-- Name: provider_signatures pk_provider_signatures; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_signatures
    ADD CONSTRAINT pk_provider_signatures PRIMARY KEY (id);


--
-- Name: provider_watermarks pk_provider_watermarks; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_watermarks
    ADD CONSTRAINT pk_provider_watermarks PRIMARY KEY (id);


--
-- Name: responsible_parties pk_responsible_parties; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.responsible_parties
    ADD CONSTRAINT pk_responsible_parties PRIMARY KEY (id);


--
-- Name: ringcentral_sms_subscriptions pk_ringcentral_sms_subscriptions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ringcentral_sms_subscriptions
    ADD CONSTRAINT pk_ringcentral_sms_subscriptions PRIMARY KEY (id);


--
-- Name: signature_audit_events pk_signature_audit_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signature_audit_events
    ADD CONSTRAINT pk_signature_audit_events PRIMARY KEY (id);


--
-- Name: sms_templates pk_sms_templates; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_templates
    ADD CONSTRAINT pk_sms_templates PRIMARY KEY (id);


--
-- Name: stored_objects pk_stored_objects; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stored_objects
    ADD CONSTRAINT pk_stored_objects PRIMARY KEY (id);


--
-- Name: support_tickets pk_support_tickets; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_tickets
    ADD CONSTRAINT pk_support_tickets PRIMARY KEY (id);


--
-- Name: time_clock_entry_edits pk_time_clock_entry_edits; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_entry_edits
    ADD CONSTRAINT pk_time_clock_entry_edits PRIMARY KEY (id);


--
-- Name: time_clock_periods pk_time_clock_periods; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_periods
    ADD CONSTRAINT pk_time_clock_periods PRIMARY KEY (id);


--
-- Name: time_clock_settings pk_time_clock_settings; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_settings
    ADD CONSTRAINT pk_time_clock_settings PRIMARY KEY (id);


--
-- Name: treatment_plan_item_icd_codes pk_treatment_plan_item_icd_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_item_icd_codes
    ADD CONSTRAINT pk_treatment_plan_item_icd_codes PRIMARY KEY (id);


--
-- Name: user_group_memberships pk_user_group_memberships; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_memberships
    ADD CONSTRAINT pk_user_group_memberships PRIMARY KEY (id);


--
-- Name: user_group_rights pk_user_group_rights; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_rights
    ADD CONSTRAINT pk_user_group_rights PRIMARY KEY (id);


--
-- Name: user_groups pk_user_groups; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_groups
    ADD CONSTRAINT pk_user_groups PRIMARY KEY (id);


--
-- Name: user_ip_rules pk_user_ip_rules; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_ip_rules
    ADD CONSTRAINT pk_user_ip_rules PRIMARY KEY (id);


--
-- Name: user_login_restrictions pk_user_login_restrictions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_login_restrictions
    ADD CONSTRAINT pk_user_login_restrictions PRIMARY KEY (id);


--
-- Name: user_preferences pk_user_preferences; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT pk_user_preferences PRIMARY KEY (id);


--
-- Name: user_presence pk_user_presence; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_presence
    ADD CONSTRAINT pk_user_presence PRIMARY KEY (tenant_id, user_id);


--
-- Name: user_tasks pk_user_tasks; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_tasks
    ADD CONSTRAINT pk_user_tasks PRIMARY KEY (id);


--
-- Name: user_time_clock_config pk_user_time_clock_config; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_time_clock_config
    ADD CONSTRAINT pk_user_time_clock_config PRIMARY KEY (id);


--
-- Name: utility_runs pk_utility_runs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.utility_runs
    ADD CONSTRAINT pk_utility_runs PRIMARY KEY (id);


--
-- Name: postcard_templates postcard_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.postcard_templates
    ADD CONSTRAINT postcard_templates_pkey PRIMARY KEY (id);


--
-- Name: prescription_library prescription_library_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescription_library
    ADD CONSTRAINT prescription_library_pkey PRIMARY KEY (id);


--
-- Name: prescriptions prescriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescriptions
    ADD CONSTRAINT prescriptions_pkey PRIMARY KEY (id);


--
-- Name: procedure_codes procedure_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_codes
    ADD CONSTRAINT procedure_codes_pkey PRIMARY KEY (code);


--
-- Name: progress_notes progress_notes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.progress_notes
    ADD CONSTRAINT progress_notes_pkey PRIMARY KEY (id);


--
-- Name: provider_insurance_ids provider_insurance_ids_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_insurance_ids
    ADD CONSTRAINT provider_insurance_ids_pkey PRIMARY KEY (id);


--
-- Name: provider_route_slips provider_route_slips_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_route_slips
    ADD CONSTRAINT provider_route_slips_pkey PRIMARY KEY (id);


--
-- Name: providers providers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT providers_pkey PRIMARY KEY (id);


--
-- Name: questionnaire_headers questionnaire_headers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.questionnaire_headers
    ADD CONSTRAINT questionnaire_headers_pkey PRIMARY KEY (id);


--
-- Name: questionnaire_options questionnaire_options_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.questionnaire_options
    ADD CONSTRAINT questionnaire_options_pkey PRIMARY KEY (id);


--
-- Name: referral_demog_details referral_demog_details_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_demog_details
    ADD CONSTRAINT referral_demog_details_pkey PRIMARY KEY (id);


--
-- Name: referral_demog_headers referral_demog_headers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_demog_headers
    ADD CONSTRAINT referral_demog_headers_pkey PRIMARY KEY (id);


--
-- Name: referrals referrals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referrals
    ADD CONSTRAINT referrals_pkey PRIMARY KEY (id);


--
-- Name: refresh_tokens refresh_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id);


--
-- Name: sms_messages sms_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_messages
    ADD CONSTRAINT sms_messages_pkey PRIMARY KEY (id);


--
-- Name: tenants tenants_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_code_key UNIQUE (code);


--
-- Name: tenants tenants_legacy_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_legacy_id_key UNIQUE (legacy_id);


--
-- Name: tenants tenants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);


--
-- Name: time_clock_entries time_clock_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_entries
    ADD CONSTRAINT time_clock_entries_pkey PRIMARY KEY (id);


--
-- Name: treatment_plan_insurance_details treatment_plan_insurance_details_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_insurance_details
    ADD CONSTRAINT treatment_plan_insurance_details_pkey PRIMARY KEY (id);


--
-- Name: treatment_plan_items treatment_plan_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_items
    ADD CONSTRAINT treatment_plan_items_pkey PRIMARY KEY (id);


--
-- Name: treatment_plans treatment_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plans
    ADD CONSTRAINT treatment_plans_pkey PRIMARY KEY (id);


--
-- Name: account_communications uq_account_communications_tenant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_communications
    ADD CONSTRAINT uq_account_communications_tenant UNIQUE (tenant_id);


--
-- Name: account_settings uq_account_settings_tenant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_settings
    ADD CONSTRAINT uq_account_settings_tenant UNIQUE (tenant_id);


--
-- Name: appointnow_reasons uq_appointnow_reasons_office_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointnow_reasons
    ADD CONSTRAINT uq_appointnow_reasons_office_code UNIQUE (office_id, reason_code);


--
-- Name: campaigns uq_campaigns_tenant_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT uq_campaigns_tenant_code UNIQUE (tenant_id, code);


--
-- Name: chart_colors uq_chart_colors_tenant_legacy; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_colors
    ADD CONSTRAINT uq_chart_colors_tenant_legacy UNIQUE (tenant_id, legacy_id);


--
-- Name: chart_materials uq_chart_materials_tenant_legacy; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_materials
    ADD CONSTRAINT uq_chart_materials_tenant_legacy UNIQUE (tenant_id, legacy_id);


--
-- Name: chart_status_templates uq_chart_status_templates_tenant_legacy; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_status_templates
    ADD CONSTRAINT uq_chart_status_templates_tenant_legacy UNIQUE (tenant_id, legacy_id);


--
-- Name: chart_tooth_notes uq_chart_tooth_notes_patient_id_tooth; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_tooth_notes
    ADD CONSTRAINT uq_chart_tooth_notes_patient_id_tooth UNIQUE (patient_id, tooth);


--
-- Name: code_bundles uq_code_bundles_tenant_legacy; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_bundles
    ADD CONSTRAINT uq_code_bundles_tenant_legacy UNIQUE (tenant_id, legacy_id);


--
-- Name: conversation_participants uq_conversation_participants_conversation_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_participants
    ADD CONSTRAINT uq_conversation_participants_conversation_user UNIQUE (conversation_id, user_id);


--
-- Name: conversations uq_conversations_tenant_dedupe_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT uq_conversations_tenant_dedupe_key UNIQUE (tenant_id, dedupe_key);


--
-- Name: definitions uq_definitions_tenant_group_key_description; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.definitions
    ADD CONSTRAINT uq_definitions_tenant_group_key_description UNIQUE (tenant_id, group_code, key1, description);


--
-- Name: dicom_instances uq_dicom_instances_sop_instance_uid; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_instances
    ADD CONSTRAINT uq_dicom_instances_sop_instance_uid UNIQUE (sop_instance_uid);


--
-- Name: dicom_series uq_dicom_series_series_instance_uid; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_series
    ADD CONSTRAINT uq_dicom_series_series_instance_uid UNIQUE (series_instance_uid);


--
-- Name: dicom_studies uq_dicom_studies_study_instance_uid; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_studies
    ADD CONSTRAINT uq_dicom_studies_study_instance_uid UNIQUE (study_instance_uid);


--
-- Name: email_messages uq_email_messages_tenant_client_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_messages
    ADD CONSTRAINT uq_email_messages_tenant_client_id UNIQUE (tenant_id, client_id);


--
-- Name: explosion_codes uq_explosion_codes_tenant_office_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.explosion_codes
    ADD CONSTRAINT uq_explosion_codes_tenant_office_code UNIQUE (tenant_id, office_id, code);


--
-- Name: fee_schedule_assignments uq_fee_schedule_assignments_tenant_legacy; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_assignments
    ADD CONSTRAINT uq_fee_schedule_assignments_tenant_legacy UNIQUE (tenant_id, legacy_id);


--
-- Name: fee_schedule_entries uq_fee_schedule_entries_schedule_code_date; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_entries
    ADD CONSTRAINT uq_fee_schedule_entries_schedule_code_date UNIQUE (fee_schedule_id, procedure_code, effective_date);


--
-- Name: fee_schedules uq_fee_schedules_tenant_legacy; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedules
    ADD CONSTRAINT uq_fee_schedules_tenant_legacy UNIQUE (tenant_id, legacy_id);


--
-- Name: message_reactions uq_message_reactions_message_user_emoji; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_reactions
    ADD CONSTRAINT uq_message_reactions_message_user_emoji UNIQUE (message_id, user_id, emoji);


--
-- Name: message_receipts uq_message_receipts_message_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_receipts
    ADD CONSTRAINT uq_message_receipts_message_user UNIQUE (message_id, user_id);


--
-- Name: message_recipient_states uq_message_recipient_states_message_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_recipient_states
    ADD CONSTRAINT uq_message_recipient_states_message_user UNIQUE (message_id, user_id);


--
-- Name: messages uq_messages_conversation_client_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT uq_messages_conversation_client_id UNIQUE (conversation_id, client_id);


--
-- Name: note_macros uq_note_macros_tenant_legacy; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_macros
    ADD CONSTRAINT uq_note_macros_tenant_legacy UNIQUE (tenant_id, legacy_id);


--
-- Name: office_advanced_settings uq_office_advanced_settings_office; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_advanced_settings
    ADD CONSTRAINT uq_office_advanced_settings_office UNIQUE (office_id);


--
-- Name: office_code_bundles uq_office_code_bundle; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_code_bundles
    ADD CONSTRAINT uq_office_code_bundle UNIQUE (office_id, bundle_id);


--
-- Name: office_integrations uq_office_integrations_office; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_integrations
    ADD CONSTRAINT uq_office_integrations_office UNIQUE (office_id);


--
-- Name: office_letter_templates uq_office_letter_template; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_letter_templates
    ADD CONSTRAINT uq_office_letter_template UNIQUE (office_id, letter_template_id);


--
-- Name: office_note_macros uq_office_note_macro; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_note_macros
    ADD CONSTRAINT uq_office_note_macro UNIQUE (office_id, note_macro_id);


--
-- Name: office_procedure_codes uq_office_procedure_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_procedure_codes
    ADD CONSTRAINT uq_office_procedure_code UNIQUE (office_id, procedure_code);


--
-- Name: office_production_types uq_office_production_type; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_production_types
    ADD CONSTRAINT uq_office_production_type UNIQUE (office_id, production_type_id);


--
-- Name: office_prescription_library uq_office_rx; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_prescription_library
    ADD CONSTRAINT uq_office_rx UNIQUE (office_id, prescription_library_id);


--
-- Name: office_schedule_days uq_office_schedule_day; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_schedule_days
    ADD CONSTRAINT uq_office_schedule_day UNIQUE (office_id, day_of_week);


--
-- Name: office_smart_assist uq_office_smart_assist_office; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_smart_assist
    ADD CONSTRAINT uq_office_smart_assist_office UNIQUE (office_id);


--
-- Name: office_statement_settings uq_office_statement_settings_office; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_statement_settings
    ADD CONSTRAINT uq_office_statement_settings_office UNIQUE (office_id);


--
-- Name: patient_insurance uq_patient_insurance_patient_slot; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_insurance
    ADD CONSTRAINT uq_patient_insurance_patient_slot UNIQUE (patient_id, legacy_plan_type, insurance_type);


--
-- Name: patient_medical_history uq_patient_medical_history_patient_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history
    ADD CONSTRAINT uq_patient_medical_history_patient_id UNIQUE (patient_id);


--
-- Name: perio_chart_templates uq_perio_chart_templates_tenant_legacy; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_chart_templates
    ADD CONSTRAINT uq_perio_chart_templates_tenant_legacy UNIQUE (tenant_id, legacy_id);


--
-- Name: perio_exam_details uq_perio_exam_details_exam_id_tooth_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_exam_details
    ADD CONSTRAINT uq_perio_exam_details_exam_id_tooth_no UNIQUE (exam_id, tooth_no);


--
-- Name: insurance_plan_frequency_groups uq_plan_frequency_groups_plan_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plan_frequency_groups
    ADD CONSTRAINT uq_plan_frequency_groups_plan_code UNIQUE (ins_plan_id, code_group);


--
-- Name: prescription_library uq_prescription_library_tenant_legacy; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescription_library
    ADD CONSTRAINT uq_prescription_library_tenant_legacy UNIQUE (tenant_id, legacy_id);


--
-- Name: procedure_fee_provenance uq_procedure_fee_provenance_procedure; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_fee_provenance
    ADD CONSTRAINT uq_procedure_fee_provenance_procedure UNIQUE (procedure_id);


--
-- Name: provider_offices uq_provider_office; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_offices
    ADD CONSTRAINT uq_provider_office UNIQUE (office_id, provider_id);


--
-- Name: provider_procedure_codes uq_provider_procedure_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_procedure_codes
    ADD CONSTRAINT uq_provider_procedure_code UNIQUE (provider_id, procedure_code);


--
-- Name: provider_referral_offices uq_provider_referral_office; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_referral_offices
    ADD CONSTRAINT uq_provider_referral_office UNIQUE (provider_id, office_id);


--
-- Name: provider_signatures uq_provider_signatures_provider; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_signatures
    ADD CONSTRAINT uq_provider_signatures_provider UNIQUE (provider_id);


--
-- Name: provider_watermarks uq_provider_watermarks_provider; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_watermarks
    ADD CONSTRAINT uq_provider_watermarks_provider UNIQUE (provider_id);


--
-- Name: ringcentral_sms_subscriptions uq_ringcentral_sms_subscriptions_subscription_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ringcentral_sms_subscriptions
    ADD CONSTRAINT uq_ringcentral_sms_subscriptions_subscription_id UNIQUE (subscription_id);


--
-- Name: sms_messages uq_sms_messages_reply_twilio_sid; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_messages
    ADD CONSTRAINT uq_sms_messages_reply_twilio_sid UNIQUE (reply_twilio_sid);


--
-- Name: sms_messages uq_sms_messages_tenant_client_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_messages
    ADD CONSTRAINT uq_sms_messages_tenant_client_id UNIQUE (tenant_id, client_id);


--
-- Name: sms_messages uq_sms_messages_twilio_sid; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_messages
    ADD CONSTRAINT uq_sms_messages_twilio_sid UNIQUE (twilio_sid);


--
-- Name: stored_objects uq_stored_objects_bucket_object_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stored_objects
    ADD CONSTRAINT uq_stored_objects_bucket_object_key UNIQUE (bucket, object_key);


--
-- Name: treatment_plan_item_icd_codes uq_treatment_plan_item_icd_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_item_icd_codes
    ADD CONSTRAINT uq_treatment_plan_item_icd_code UNIQUE (plan_item_id, icd_code_id);


--
-- Name: user_group_memberships uq_user_group_memberships_user_group; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_memberships
    ADD CONSTRAINT uq_user_group_memberships_user_group UNIQUE (user_id, group_id);


--
-- Name: user_group_rights uq_user_group_rights_group_permission; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_rights
    ADD CONSTRAINT uq_user_group_rights_group_permission UNIQUE (group_id, permission_id);


--
-- Name: user_login_restrictions uq_user_login_restrictions_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_login_restrictions
    ADD CONSTRAINT uq_user_login_restrictions_user UNIQUE (user_id);


--
-- Name: user_preferences uq_user_preferences_user_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT uq_user_preferences_user_key UNIQUE (user_id, pref_key);


--
-- Name: user_time_clock_config uq_user_time_clock_config_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_time_clock_config
    ADD CONSTRAINT uq_user_time_clock_config_user UNIQUE (user_id);


--
-- Name: users uq_users_tenant_short_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_tenant_short_id UNIQUE (tenant_id, short_id);


--
-- Name: user_offices user_offices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_offices
    ADD CONSTRAINT user_offices_pkey PRIMARY KEY (id);


--
-- Name: user_offices user_offices_user_id_office_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_offices
    ADD CONSTRAINT user_offices_user_id_office_id_key UNIQUE (user_id, office_id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: idx_acct_notes_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_acct_notes_patient ON public.account_notes USING btree (patient_id);


--
-- Name: idx_alerts_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_patient ON public.patient_alerts USING btree (patient_id);


--
-- Name: idx_alloc_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alloc_patient ON public.payment_allocations USING btree (patient_id);


--
-- Name: idx_alloc_payment; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alloc_payment ON public.payment_allocations USING btree (payment_id);


--
-- Name: idx_alloc_proc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alloc_proc ON public.payment_allocations USING btree (procedure_id);


--
-- Name: idx_appt_archived; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_appt_archived ON public.appointments USING btree (is_archived);


--
-- Name: idx_appt_date_office; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_appt_date_office ON public.appointments USING btree (date, office_id);


--
-- Name: idx_appt_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_appt_legacy ON public.appointments USING btree (legacy_id);


--
-- Name: idx_appt_operatory_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_appt_operatory_date ON public.appointments USING btree (operatory_id, date);


--
-- Name: idx_appt_patient_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_appt_patient_date ON public.appointments USING btree (patient_id, date);


--
-- Name: idx_appt_proc_appt; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_appt_proc_appt ON public.appointment_procedures USING btree (appointment_id);


--
-- Name: idx_appt_provider_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_appt_provider_date ON public.appointments USING btree (provider_id, date);


--
-- Name: idx_appt_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_appt_status ON public.appointments USING btree (status);


--
-- Name: idx_bundle_items_bundle; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bundle_items_bundle ON public.code_bundle_items USING btree (bundle_id);


--
-- Name: idx_caries_risk_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_caries_risk_patient ON public.caries_risk_assessments USING btree (patient_id, risk_date);


--
-- Name: idx_carriers_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_carriers_legacy ON public.insurance_carriers USING btree (legacy_id);


--
-- Name: idx_chart_colors_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chart_colors_tenant ON public.chart_colors USING btree (tenant_id);


--
-- Name: idx_chart_cond_patient_tooth; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chart_cond_patient_tooth ON public.chart_conditions USING btree (patient_id, tooth);


--
-- Name: idx_claim_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_claim_legacy ON public.insurance_claims USING btree (legacy_id);


--
-- Name: idx_claim_patient_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_claim_patient_status ON public.insurance_claims USING btree (patient_id, status);


--
-- Name: idx_claim_sub_claim; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_claim_sub_claim ON public.claim_submissions USING btree (claim_id);


--
-- Name: idx_codes_view_office; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_codes_view_office ON public.codes_view USING btree (office_id);


--
-- Name: idx_cov_rules_plan; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cov_rules_plan ON public.insurance_coverage_rules USING btree (ins_plan_id);


--
-- Name: idx_def_group; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_def_group ON public.definitions USING btree (tenant_id, group_code);


--
-- Name: idx_employers_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_employers_legacy ON public.employers USING btree (legacy_id);


--
-- Name: idx_fee_assign_plan; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fee_assign_plan ON public.fee_schedule_assignments USING btree (ins_plan_id);


--
-- Name: idx_fee_assign_sched; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fee_assign_sched ON public.fee_schedule_assignments USING btree (fee_schedule_id);


--
-- Name: idx_fee_sched_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fee_sched_legacy ON public.fee_schedules USING btree (legacy_id);


--
-- Name: idx_image_details_group; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_image_details_group ON public.image_details USING btree (image_group_id);


--
-- Name: idx_image_groups_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_image_groups_patient ON public.image_groups USING btree (patient_id);


--
-- Name: idx_ins_plans_carrier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ins_plans_carrier ON public.insurance_plans USING btree (carrier_id);


--
-- Name: idx_ins_plans_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ins_plans_legacy ON public.insurance_plans USING btree (legacy_id);


--
-- Name: idx_ins_sub_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ins_sub_legacy ON public.insurance_subscribers USING btree (legacy_id);


--
-- Name: idx_ins_sub_plan; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ins_sub_plan ON public.insurance_subscribers USING btree (ins_plan_id);


--
-- Name: idx_ledger_ins_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ledger_ins_legacy ON public.ledger_insurance_details USING btree (legacy_ledger_id);


--
-- Name: idx_ledger_ins_proc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ledger_ins_proc ON public.ledger_insurance_details USING btree (procedure_id);


--
-- Name: idx_med_hist_detail_header; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_med_hist_detail_header ON public.medical_history_details USING btree (history_id);


--
-- Name: idx_offices_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_offices_tenant ON public.offices USING btree (tenant_id);


--
-- Name: idx_operatories_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_operatories_legacy ON public.operatories USING btree (legacy_id);


--
-- Name: idx_operatories_office; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_operatories_office ON public.operatories USING btree (office_id);


--
-- Name: idx_ortho_plans_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ortho_plans_patient ON public.ortho_plans USING btree (patient_id);


--
-- Name: idx_pat_ins_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pat_ins_patient ON public.patient_insurance USING btree (patient_id);


--
-- Name: idx_pat_ins_payplan_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pat_ins_payplan_patient ON public.patient_ins_payment_plans USING btree (patient_id);


--
-- Name: idx_pat_notes_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pat_notes_patient ON public.patient_notes USING btree (patient_id, note_date);


--
-- Name: idx_pat_payplan_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pat_payplan_patient ON public.patient_payment_plans USING btree (patient_id);


--
-- Name: idx_pat_recall_due; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pat_recall_due ON public.patient_recalls USING btree (due_date, status);


--
-- Name: idx_pat_recall_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pat_recall_patient ON public.patient_recalls USING btree (patient_id);


--
-- Name: idx_pat_regplan_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pat_regplan_patient ON public.patient_reg_plans USING btree (patient_id);


--
-- Name: idx_pat_sec_ins_payplan_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pat_sec_ins_payplan_patient ON public.patient_sec_ins_payment_plans USING btree (patient_id);


--
-- Name: idx_patients_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_patients_legacy ON public.patients USING btree (legacy_id);


--
-- Name: idx_patients_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_patients_name ON public.patients USING btree (last_name, first_name);


--
-- Name: idx_patients_office; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_patients_office ON public.patients USING btree (home_office_id);


--
-- Name: idx_patients_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_patients_tenant ON public.patients USING btree (tenant_id);


--
-- Name: idx_payment_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_payment_legacy ON public.patient_payments USING btree (legacy_id);


--
-- Name: idx_payment_patient_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_payment_patient_date ON public.patient_payments USING btree (patient_id, payment_date);


--
-- Name: idx_perio_activity_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_perio_activity_patient ON public.perio_chart_activity USING btree (patient_id, activity_date);


--
-- Name: idx_perio_detail_exam; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_perio_detail_exam ON public.perio_exam_details USING btree (exam_id);


--
-- Name: idx_perio_patient_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_perio_patient_date ON public.perio_exams USING btree (patient_id, exam_date);


--
-- Name: idx_pnote_patient_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pnote_patient_date ON public.progress_notes USING btree (patient_id, note_date);


--
-- Name: idx_proc_claim; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_proc_claim ON public.patient_procedures USING btree (claim_id);


--
-- Name: idx_proc_codes_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_proc_codes_category ON public.procedure_codes USING btree (category);


--
-- Name: idx_proc_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_proc_legacy ON public.patient_procedures USING btree (legacy_id);


--
-- Name: idx_proc_patient_dos; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_proc_patient_dos ON public.patient_procedures USING btree (patient_id, date_of_service);


--
-- Name: idx_proc_void; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_proc_void ON public.patient_procedures USING btree (is_void);


--
-- Name: idx_prov_ins_id_carrier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_prov_ins_id_carrier ON public.provider_insurance_ids USING btree (carrier_id);


--
-- Name: idx_prov_ins_id_prov; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_prov_ins_id_prov ON public.provider_insurance_ids USING btree (provider_id);


--
-- Name: idx_providers_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_providers_legacy ON public.providers USING btree (legacy_id);


--
-- Name: idx_providers_office; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_providers_office ON public.providers USING btree (office_id);


--
-- Name: idx_q_opts_q; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_q_opts_q ON public.questionnaire_options USING btree (questionnaire_id);


--
-- Name: idx_ref_demog_detail_ref; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ref_demog_detail_ref ON public.referral_demog_details USING btree (referral_id);


--
-- Name: idx_route_slip_provider; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_route_slip_provider ON public.provider_route_slips USING btree (provider_id);


--
-- Name: idx_rtoken_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rtoken_user ON public.refresh_tokens USING btree (user_id);


--
-- Name: idx_rx_patient_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rx_patient_date ON public.prescriptions USING btree (patient_id, rx_date);


--
-- Name: idx_sigs_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sigs_patient ON public.patient_signatures USING btree (patient_id);


--
-- Name: idx_sms_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sms_patient ON public.sms_messages USING btree (patient_id, created_at);


--
-- Name: idx_tclock_user_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tclock_user_date ON public.time_clock_entries USING btree (user_id, clock_in);


--
-- Name: idx_tp_ins_detail_item; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tp_ins_detail_item ON public.treatment_plan_insurance_details USING btree (plan_item_id);


--
-- Name: idx_txitem_plan; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_txitem_plan ON public.treatment_plan_items USING btree (plan_id);


--
-- Name: idx_txplan_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_txplan_legacy ON public.treatment_plans USING btree (legacy_id);


--
-- Name: idx_txplan_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_txplan_patient ON public.treatment_plans USING btree (patient_id);


--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_email ON public.users USING btree (email);


--
-- Name: idx_users_legacy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_legacy ON public.users USING btree (legacy_id);


--
-- Name: idx_users_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_tenant ON public.users USING btree (tenant_id);


--
-- Name: ix_account_communications_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_account_communications_tenant_id ON public.account_communications USING btree (tenant_id);


--
-- Name: ix_account_consents_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_account_consents_is_active ON public.account_consents USING btree (is_active);


--
-- Name: ix_account_consents_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_account_consents_tenant_id ON public.account_consents USING btree (tenant_id);


--
-- Name: ix_account_holidays_holiday_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_account_holidays_holiday_date ON public.account_holidays USING btree (holiday_date);


--
-- Name: ix_account_holidays_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_account_holidays_office_id ON public.account_holidays USING btree (office_id);


--
-- Name: ix_account_holidays_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_account_holidays_tenant_id ON public.account_holidays USING btree (tenant_id);


--
-- Name: ix_account_settings_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_account_settings_tenant_id ON public.account_settings USING btree (tenant_id);


--
-- Name: ix_appointment_procedures_treatment_plan_item_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appointment_procedures_treatment_plan_item_id ON public.appointment_procedures USING btree (treatment_plan_item_id);


--
-- Name: ix_appointments_lab_vendor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appointments_lab_vendor_id ON public.appointments USING btree (lab_vendor_id);


--
-- Name: ix_appointments_office_has_lab; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appointments_office_has_lab ON public.appointments USING btree (office_id, has_lab);


--
-- Name: ix_appointnow_reasons_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appointnow_reasons_office_id ON public.appointnow_reasons USING btree (office_id);


--
-- Name: ix_appointnow_reasons_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appointnow_reasons_tenant_id ON public.appointnow_reasons USING btree (tenant_id);


--
-- Name: ix_audit_logs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_created_at ON public.audit_logs USING btree (created_at);


--
-- Name: ix_audit_logs_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_office_id ON public.audit_logs USING btree (office_id);


--
-- Name: ix_audit_logs_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_patient_id ON public.audit_logs USING btree (patient_id);


--
-- Name: ix_audit_logs_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_resource ON public.audit_logs USING btree (resource_type, resource_id);


--
-- Name: ix_audit_logs_resource_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_resource_type ON public.audit_logs USING btree (resource_type);


--
-- Name: ix_audit_logs_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_tenant_id ON public.audit_logs USING btree (tenant_id);


--
-- Name: ix_audit_logs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_user_id ON public.audit_logs USING btree (user_id);


--
-- Name: ix_auth_action_tokens_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_auth_action_tokens_token_hash ON public.auth_action_tokens USING btree (token_hash);


--
-- Name: ix_auth_action_tokens_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_action_tokens_user_id ON public.auth_action_tokens USING btree (user_id);


--
-- Name: ix_booking_requests_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_booking_requests_office_id ON public.booking_requests USING btree (office_id);


--
-- Name: ix_booking_requests_office_slot; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_booking_requests_office_slot ON public.booking_requests USING btree (tenant_id, office_id, slot_date);


--
-- Name: ix_booking_requests_office_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_booking_requests_office_status ON public.booking_requests USING btree (tenant_id, office_id, status, created_at);


--
-- Name: ix_booking_requests_payment_link_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_booking_requests_payment_link_id ON public.booking_requests USING btree (payment_link_id);


--
-- Name: ix_booking_requests_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_booking_requests_tenant_id ON public.booking_requests USING btree (tenant_id);


--
-- Name: ix_campaigns_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_campaigns_code ON public.campaigns USING btree (code);


--
-- Name: ix_campaigns_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_campaigns_tenant_id ON public.campaigns USING btree (tenant_id);


--
-- Name: ix_chart_conditions_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chart_conditions_group_id ON public.chart_conditions USING btree (group_id);


--
-- Name: ix_chart_conditions_patient_is_inactive; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chart_conditions_patient_is_inactive ON public.chart_conditions USING btree (patient_id, is_inactive);


--
-- Name: ix_chart_conditions_patient_procedure_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chart_conditions_patient_procedure_code ON public.chart_conditions USING btree (patient_id, procedure_code);


--
-- Name: ix_chart_status_templates_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chart_status_templates_tenant_id ON public.chart_status_templates USING btree (tenant_id);


--
-- Name: ix_chart_tooth_notes_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chart_tooth_notes_patient_id ON public.chart_tooth_notes USING btree (patient_id);


--
-- Name: ix_claim_attachments_claim_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_claim_attachments_claim_id ON public.claim_attachments USING btree (claim_id);


--
-- Name: ix_claim_attachments_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_claim_attachments_tenant_id ON public.claim_attachments USING btree (tenant_id);


--
-- Name: ix_consent_signatures_consent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_consent_signatures_consent_id ON public.consent_signatures USING btree (consent_id);


--
-- Name: ix_consent_signatures_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_consent_signatures_tenant_id ON public.consent_signatures USING btree (tenant_id);


--
-- Name: ix_conversation_participants_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversation_participants_conversation_id ON public.conversation_participants USING btree (conversation_id);


--
-- Name: ix_conversation_participants_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversation_participants_tenant_id ON public.conversation_participants USING btree (tenant_id);


--
-- Name: ix_conversation_participants_tenant_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversation_participants_tenant_user ON public.conversation_participants USING btree (tenant_id, user_id);


--
-- Name: ix_conversation_participants_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversation_participants_user_id ON public.conversation_participants USING btree (user_id);


--
-- Name: ix_conversations_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversations_tenant_id ON public.conversations USING btree (tenant_id);


--
-- Name: ix_conversations_tenant_last_message_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversations_tenant_last_message_at ON public.conversations USING btree (tenant_id, last_message_at);


--
-- Name: ix_dicom_instances_series_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dicom_instances_series_id ON public.dicom_instances USING btree (series_id);


--
-- Name: ix_dicom_instances_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dicom_instances_tenant_id ON public.dicom_instances USING btree (tenant_id);


--
-- Name: ix_dicom_series_study_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dicom_series_study_id ON public.dicom_series USING btree (study_id);


--
-- Name: ix_dicom_series_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dicom_series_tenant_id ON public.dicom_series USING btree (tenant_id);


--
-- Name: ix_dicom_studies_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dicom_studies_patient_id ON public.dicom_studies USING btree (patient_id);


--
-- Name: ix_dicom_studies_study_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dicom_studies_study_date ON public.dicom_studies USING btree (study_date);


--
-- Name: ix_dicom_studies_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dicom_studies_tenant_id ON public.dicom_studies USING btree (tenant_id);


--
-- Name: ix_dicom_studies_tenant_patient_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dicom_studies_tenant_patient_date ON public.dicom_studies USING btree (tenant_id, patient_id, study_date);


--
-- Name: ix_eligibility_checks_subscriber_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_eligibility_checks_subscriber_id ON public.eligibility_checks USING btree (subscriber_id);


--
-- Name: ix_eligibility_checks_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_eligibility_checks_tenant_id ON public.eligibility_checks USING btree (tenant_id);


--
-- Name: ix_email_messages_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_email_messages_patient_id ON public.email_messages USING btree (patient_id);


--
-- Name: ix_email_messages_provider_message_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_email_messages_provider_message_id ON public.email_messages USING btree (provider_message_id);


--
-- Name: ix_email_messages_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_email_messages_tenant_id ON public.email_messages USING btree (tenant_id);


--
-- Name: ix_explosion_code_items_explosion_code_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_explosion_code_items_explosion_code_id ON public.explosion_code_items USING btree (explosion_code_id);


--
-- Name: ix_explosion_codes_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_explosion_codes_tenant_id ON public.explosion_codes USING btree (tenant_id);


--
-- Name: ix_fee_schedule_assignments_carrier_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fee_schedule_assignments_carrier_id ON public.fee_schedule_assignments USING btree (carrier_id);


--
-- Name: ix_fee_schedule_entries_procedure_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fee_schedule_entries_procedure_code ON public.fee_schedule_entries USING btree (procedure_code);


--
-- Name: ix_fee_schedule_entries_schedule_code_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fee_schedule_entries_schedule_code_date ON public.fee_schedule_entries USING btree (fee_schedule_id, procedure_code, effective_date DESC);


--
-- Name: ix_fee_schedule_entries_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fee_schedule_entries_tenant_id ON public.fee_schedule_entries USING btree (tenant_id);


--
-- Name: ix_icd_codes_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icd_codes_code ON public.icd_codes USING btree (code);


--
-- Name: ix_insurance_claims_ins_plan_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_insurance_claims_ins_plan_id ON public.insurance_claims USING btree (ins_plan_id);


--
-- Name: ix_insurance_plan_frequency_groups_ins_plan_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_insurance_plan_frequency_groups_ins_plan_id ON public.insurance_plan_frequency_groups USING btree (ins_plan_id);


--
-- Name: ix_insurance_plan_frequency_groups_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_insurance_plan_frequency_groups_tenant_id ON public.insurance_plan_frequency_groups USING btree (tenant_id);


--
-- Name: ix_insurance_plans_tenant_group_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_insurance_plans_tenant_group_number ON public.insurance_plans USING btree (tenant_id, group_number);


--
-- Name: ix_labs_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_labs_name ON public.labs USING btree (name);


--
-- Name: ix_labs_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_labs_tenant_id ON public.labs USING btree (tenant_id);


--
-- Name: ix_ledger_insurance_details_claim_id_is_void; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ledger_insurance_details_claim_id_is_void ON public.ledger_insurance_details USING btree (claim_id, is_void);


--
-- Name: ix_letter_batch_items_batch_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_letter_batch_items_batch_id ON public.letter_batch_items USING btree (batch_id);


--
-- Name: ix_letter_batch_items_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_letter_batch_items_patient_id ON public.letter_batch_items USING btree (patient_id);


--
-- Name: ix_letter_batch_runs_template_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_letter_batch_runs_template_id ON public.letter_batch_runs USING btree (template_id);


--
-- Name: ix_letter_batch_runs_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_letter_batch_runs_tenant_id ON public.letter_batch_runs USING btree (tenant_id);


--
-- Name: ix_medical_history_details_answer_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_medical_history_details_answer_type ON public.medical_history_details USING btree (answer_type);


--
-- Name: ix_medical_history_records_content_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_medical_history_records_content_hash ON public.medical_history_records USING btree (content_hash);


--
-- Name: ix_medical_history_records_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_medical_history_records_tenant_id ON public.medical_history_records USING btree (tenant_id);


--
-- Name: ix_message_attachments_message; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_message_attachments_message ON public.message_attachments USING btree (message_id);


--
-- Name: ix_message_attachments_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_message_attachments_tenant_id ON public.message_attachments USING btree (tenant_id);


--
-- Name: ix_message_reactions_message; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_message_reactions_message ON public.message_reactions USING btree (message_id);


--
-- Name: ix_message_reactions_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_message_reactions_tenant_id ON public.message_reactions USING btree (tenant_id);


--
-- Name: ix_message_receipts_message_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_message_receipts_message_id ON public.message_receipts USING btree (message_id);


--
-- Name: ix_message_receipts_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_message_receipts_tenant_id ON public.message_receipts USING btree (tenant_id);


--
-- Name: ix_message_receipts_user_delivered; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_message_receipts_user_delivered ON public.message_receipts USING btree (user_id, delivered_at);


--
-- Name: ix_message_receipts_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_message_receipts_user_id ON public.message_receipts USING btree (user_id);


--
-- Name: ix_message_recipient_states_message_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_message_recipient_states_message_id ON public.message_recipient_states USING btree (message_id);


--
-- Name: ix_message_recipient_states_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_message_recipient_states_tenant_id ON public.message_recipient_states USING btree (tenant_id);


--
-- Name: ix_message_recipient_states_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_message_recipient_states_user_id ON public.message_recipient_states USING btree (user_id);


--
-- Name: ix_messages_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_messages_conversation_id ON public.messages USING btree (conversation_id);


--
-- Name: ix_messages_conversation_id_desc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_messages_conversation_id_desc ON public.messages USING btree (conversation_id, id);


--
-- Name: ix_messages_sender_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_messages_sender_id ON public.messages USING btree (sender_id);


--
-- Name: ix_messages_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_messages_tenant_id ON public.messages USING btree (tenant_id);


--
-- Name: ix_mig_manifest_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mig_manifest_patient ON public.mig_dicom_manifest USING btree (patient_id);


--
-- Name: ix_mig_manifest_sha; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mig_manifest_sha ON public.mig_dicom_manifest USING btree (content_sha256);


--
-- Name: ix_mig_manifest_study; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mig_manifest_study ON public.mig_dicom_manifest USING btree (study_instance_uid);


--
-- Name: ix_notifications_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_tenant_id ON public.notifications USING btree (tenant_id);


--
-- Name: ix_notifications_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_user_id ON public.notifications USING btree (user_id);


--
-- Name: ix_office_advanced_settings_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_advanced_settings_office_id ON public.office_advanced_settings USING btree (office_id);


--
-- Name: ix_office_advanced_settings_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_advanced_settings_tenant_id ON public.office_advanced_settings USING btree (tenant_id);


--
-- Name: ix_office_code_bundles_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_code_bundles_office_id ON public.office_code_bundles USING btree (office_id);


--
-- Name: ix_office_code_bundles_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_code_bundles_tenant_id ON public.office_code_bundles USING btree (tenant_id);


--
-- Name: ix_office_integrations_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_integrations_office_id ON public.office_integrations USING btree (office_id);


--
-- Name: ix_office_integrations_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_integrations_tenant_id ON public.office_integrations USING btree (tenant_id);


--
-- Name: ix_office_letter_templates_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_letter_templates_office_id ON public.office_letter_templates USING btree (office_id);


--
-- Name: ix_office_letter_templates_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_letter_templates_tenant_id ON public.office_letter_templates USING btree (tenant_id);


--
-- Name: ix_office_note_macros_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_note_macros_office_id ON public.office_note_macros USING btree (office_id);


--
-- Name: ix_office_note_macros_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_note_macros_tenant_id ON public.office_note_macros USING btree (tenant_id);


--
-- Name: ix_office_phone_assignments_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_phone_assignments_office_id ON public.office_phone_assignments USING btree (office_id);


--
-- Name: ix_office_phone_assignments_phone_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_phone_assignments_phone_number ON public.office_phone_assignments USING btree (phone_number);


--
-- Name: ix_office_phone_assignments_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_phone_assignments_tenant_id ON public.office_phone_assignments USING btree (tenant_id);


--
-- Name: ix_office_prescription_library_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_prescription_library_office_id ON public.office_prescription_library USING btree (office_id);


--
-- Name: ix_office_prescription_library_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_prescription_library_tenant_id ON public.office_prescription_library USING btree (tenant_id);


--
-- Name: ix_office_procedure_codes_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_procedure_codes_office_id ON public.office_procedure_codes USING btree (office_id);


--
-- Name: ix_office_procedure_codes_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_procedure_codes_tenant_id ON public.office_procedure_codes USING btree (tenant_id);


--
-- Name: ix_office_production_types_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_production_types_office_id ON public.office_production_types USING btree (office_id);


--
-- Name: ix_office_production_types_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_production_types_tenant_id ON public.office_production_types USING btree (tenant_id);


--
-- Name: ix_office_schedule_days_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_schedule_days_office_id ON public.office_schedule_days USING btree (office_id);


--
-- Name: ix_office_schedule_days_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_schedule_days_tenant_id ON public.office_schedule_days USING btree (tenant_id);


--
-- Name: ix_office_smart_assist_items_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_smart_assist_items_office_id ON public.office_smart_assist_items USING btree (office_id);


--
-- Name: ix_office_smart_assist_items_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_smart_assist_items_tenant_id ON public.office_smart_assist_items USING btree (tenant_id);


--
-- Name: ix_office_smart_assist_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_smart_assist_office_id ON public.office_smart_assist USING btree (office_id);


--
-- Name: ix_office_smart_assist_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_smart_assist_tenant_id ON public.office_smart_assist USING btree (tenant_id);


--
-- Name: ix_office_statement_settings_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_statement_settings_office_id ON public.office_statement_settings USING btree (office_id);


--
-- Name: ix_office_statement_settings_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_office_statement_settings_tenant_id ON public.office_statement_settings USING btree (tenant_id);


--
-- Name: ix_patient_adjustments_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_adjustments_patient_id ON public.patient_adjustments USING btree (patient_id);


--
-- Name: ix_patient_adjustments_procedure_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_adjustments_procedure_id ON public.patient_adjustments USING btree (procedure_id);


--
-- Name: ix_patient_adjustments_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_adjustments_tenant_id ON public.patient_adjustments USING btree (tenant_id);


--
-- Name: ix_patient_alerts_source_medical_alert_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_alerts_source_medical_alert_id ON public.patient_alerts USING btree (source_medical_alert_id);


--
-- Name: ix_patient_consents_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_consents_patient_id ON public.patient_consents USING btree (patient_id);


--
-- Name: ix_patient_consents_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_consents_tenant_id ON public.patient_consents USING btree (tenant_id);


--
-- Name: ix_patient_documents_claim_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_documents_claim_id ON public.patient_documents USING btree (claim_id);


--
-- Name: ix_patient_documents_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_documents_patient_id ON public.patient_documents USING btree (patient_id);


--
-- Name: ix_patient_documents_patient_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_documents_patient_type ON public.patient_documents USING btree (patient_id, document_type);


--
-- Name: ix_patient_documents_procedure_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_documents_procedure_id ON public.patient_documents USING btree (procedure_id);


--
-- Name: ix_patient_documents_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_documents_tenant_id ON public.patient_documents USING btree (tenant_id);


--
-- Name: ix_patient_emergency_contacts_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_emergency_contacts_patient_id ON public.patient_emergency_contacts USING btree (patient_id);


--
-- Name: ix_patient_emergency_contacts_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_emergency_contacts_tenant_id ON public.patient_emergency_contacts USING btree (tenant_id);


--
-- Name: ix_patient_ins_payment_plans_ortho_plan_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_ins_payment_plans_ortho_plan_id ON public.patient_ins_payment_plans USING btree (ortho_plan_id);


--
-- Name: ix_patient_insurance_ins_plan_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_insurance_ins_plan_id ON public.patient_insurance USING btree (ins_plan_id);


--
-- Name: ix_patient_insurance_legacy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_insurance_legacy_id ON public.patient_insurance USING btree (legacy_id);


--
-- Name: ix_patient_medical_alerts_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_medical_alerts_patient_id ON public.patient_medical_alerts USING btree (patient_id);


--
-- Name: ix_patient_medical_alerts_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_medical_alerts_tenant_id ON public.patient_medical_alerts USING btree (tenant_id);


--
-- Name: ix_patient_medical_history_events_entity_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_medical_history_events_entity_type ON public.patient_medical_history_events USING btree (entity_type);


--
-- Name: ix_patient_medical_history_events_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_medical_history_events_patient_id ON public.patient_medical_history_events USING btree (patient_id);


--
-- Name: ix_patient_medical_history_events_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_medical_history_events_tenant_id ON public.patient_medical_history_events USING btree (tenant_id);


--
-- Name: ix_patient_medical_history_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_medical_history_patient_id ON public.patient_medical_history USING btree (patient_id);


--
-- Name: ix_patient_medical_history_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_medical_history_tenant_id ON public.patient_medical_history USING btree (tenant_id);


--
-- Name: ix_patient_notes_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_notes_document_id ON public.patient_notes USING btree (document_id);


--
-- Name: ix_patient_opening_balances_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_patient_opening_balances_patient_id ON public.patient_opening_balances USING btree (patient_id);


--
-- Name: ix_patient_opening_balances_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_opening_balances_tenant_id ON public.patient_opening_balances USING btree (tenant_id);


--
-- Name: ix_patient_payment_plans_treatment_plan_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_payment_plans_treatment_plan_id ON public.patient_payment_plans USING btree (treatment_plan_id);


--
-- Name: ix_patient_payments_patient_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_payments_patient_date ON public.patient_payments USING btree (patient_id, payment_date);


--
-- Name: ix_patient_plan_installments_ortho_plan_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_plan_installments_ortho_plan_id ON public.patient_plan_installments USING btree (ortho_plan_id);


--
-- Name: ix_patient_plan_installments_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_plan_installments_patient_id ON public.patient_plan_installments USING btree (patient_id);


--
-- Name: ix_patient_plan_installments_payment_plan_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_plan_installments_payment_plan_id ON public.patient_plan_installments USING btree (payment_plan_id);


--
-- Name: ix_patient_plan_installments_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_plan_installments_tenant_id ON public.patient_plan_installments USING btree (tenant_id);


--
-- Name: ix_patient_procedures_patient_dos; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_procedures_patient_dos ON public.patient_procedures USING btree (patient_id, date_of_service);


--
-- Name: ix_patient_procedures_treatment_plan_item_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_procedures_treatment_plan_item_id ON public.patient_procedures USING btree (treatment_plan_item_id);


--
-- Name: ix_patient_questionnaire_responses_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_questionnaire_responses_patient_id ON public.patient_questionnaire_responses USING btree (patient_id);


--
-- Name: ix_patient_questionnaire_responses_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_questionnaire_responses_tenant_id ON public.patient_questionnaire_responses USING btree (tenant_id);


--
-- Name: ix_patient_refunds_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_refunds_patient_id ON public.patient_refunds USING btree (patient_id);


--
-- Name: ix_patient_refunds_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_refunds_tenant_id ON public.patient_refunds USING btree (tenant_id);


--
-- Name: ix_patient_sec_ins_payment_plans_ortho_plan_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_sec_ins_payment_plans_ortho_plan_id ON public.patient_sec_ins_payment_plans USING btree (ortho_plan_id);


--
-- Name: ix_patient_signatures_claim_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_signatures_claim_id ON public.patient_signatures USING btree (claim_id);


--
-- Name: ix_patient_signatures_consent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_signatures_consent_id ON public.patient_signatures USING btree (consent_id);


--
-- Name: ix_patient_signatures_progress_note_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_signatures_progress_note_id ON public.patient_signatures USING btree (progress_note_id);


--
-- Name: ix_patient_signatures_signature_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_signatures_signature_type ON public.patient_signatures USING btree (signature_type);


--
-- Name: ix_patient_signatures_signer_provider_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_signatures_signer_provider_id ON public.patient_signatures USING btree (signer_provider_id);


--
-- Name: ix_patient_statements_batch_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_statements_batch_id ON public.patient_statements USING btree (batch_id);


--
-- Name: ix_patient_statements_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_statements_patient_id ON public.patient_statements USING btree (patient_id);


--
-- Name: ix_patient_statements_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_statements_tenant_id ON public.patient_statements USING btree (tenant_id);


--
-- Name: ix_payment_allocations_adjustment_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_payment_allocations_adjustment_id ON public.payment_allocations USING btree (adjustment_id);


--
-- Name: ix_payment_allocations_procedure_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_payment_allocations_procedure_id ON public.payment_allocations USING btree (procedure_id);


--
-- Name: ix_perio_chart_templates_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_perio_chart_templates_tenant_id ON public.perio_chart_templates USING btree (tenant_id);


--
-- Name: ix_perio_exams_provider_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_perio_exams_provider_id ON public.perio_exams USING btree (provider_id);


--
-- Name: ix_permissions_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_permissions_category ON public.permissions USING btree (category);


--
-- Name: ix_permissions_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_permissions_code ON public.permissions USING btree (code);


--
-- Name: ix_place_of_service_codes_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_place_of_service_codes_code ON public.place_of_service_codes USING btree (code);


--
-- Name: ix_place_of_service_codes_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_place_of_service_codes_tenant_id ON public.place_of_service_codes USING btree (tenant_id);


--
-- Name: ix_plan_frequency_groups_tenant_plan; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_plan_frequency_groups_tenant_plan ON public.insurance_plan_frequency_groups USING btree (tenant_id, ins_plan_id);


--
-- Name: ix_procedure_codes_coverage_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_procedure_codes_coverage_category ON public.procedure_codes USING btree (coverage_category);


--
-- Name: ix_procedure_fee_provenance_legacy_ledger_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_procedure_fee_provenance_legacy_ledger_id ON public.procedure_fee_provenance USING btree (legacy_ledger_id);


--
-- Name: ix_procedure_fee_provenance_procedure_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_procedure_fee_provenance_procedure_id ON public.procedure_fee_provenance USING btree (procedure_id);


--
-- Name: ix_procedure_fee_provenance_schedule; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_procedure_fee_provenance_schedule ON public.procedure_fee_provenance USING btree (fee_schedule_id);


--
-- Name: ix_procedure_insurance_rules_procedure_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_procedure_insurance_rules_procedure_code ON public.procedure_insurance_rules USING btree (procedure_code);


--
-- Name: ix_procedure_insurance_rules_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_procedure_insurance_rules_tenant_id ON public.procedure_insurance_rules USING btree (tenant_id);


--
-- Name: ix_production_types_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_production_types_tenant_id ON public.production_types USING btree (tenant_id);


--
-- Name: ix_progress_note_attachments_progress_note_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_progress_note_attachments_progress_note_id ON public.progress_note_attachments USING btree (progress_note_id);


--
-- Name: ix_progress_note_attachments_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_progress_note_attachments_tenant_id ON public.progress_note_attachments USING btree (tenant_id);


--
-- Name: ix_provider_carrier_logins_carrier_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_carrier_logins_carrier_id ON public.provider_carrier_logins USING btree (carrier_id);


--
-- Name: ix_provider_carrier_logins_provider_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_carrier_logins_provider_id ON public.provider_carrier_logins USING btree (provider_id);


--
-- Name: ix_provider_carrier_logins_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_carrier_logins_tenant_id ON public.provider_carrier_logins USING btree (tenant_id);


--
-- Name: ix_provider_holidays_holiday_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_holidays_holiday_date ON public.provider_holidays USING btree (holiday_date);


--
-- Name: ix_provider_holidays_provider_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_holidays_provider_id ON public.provider_holidays USING btree (provider_id);


--
-- Name: ix_provider_holidays_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_holidays_tenant_id ON public.provider_holidays USING btree (tenant_id);


--
-- Name: ix_provider_offices_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_offices_office_id ON public.provider_offices USING btree (office_id);


--
-- Name: ix_provider_offices_provider_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_offices_provider_id ON public.provider_offices USING btree (provider_id);


--
-- Name: ix_provider_offices_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_offices_tenant_id ON public.provider_offices USING btree (tenant_id);


--
-- Name: ix_provider_procedure_codes_procedure_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_procedure_codes_procedure_code ON public.provider_procedure_codes USING btree (procedure_code);


--
-- Name: ix_provider_procedure_codes_provider_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_procedure_codes_provider_id ON public.provider_procedure_codes USING btree (provider_id);


--
-- Name: ix_provider_procedure_codes_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_procedure_codes_tenant_id ON public.provider_procedure_codes USING btree (tenant_id);


--
-- Name: ix_provider_referral_offices_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_referral_offices_office_id ON public.provider_referral_offices USING btree (office_id);


--
-- Name: ix_provider_referral_offices_provider_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_referral_offices_provider_id ON public.provider_referral_offices USING btree (provider_id);


--
-- Name: ix_provider_referral_offices_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_referral_offices_tenant_id ON public.provider_referral_offices USING btree (tenant_id);


--
-- Name: ix_provider_schedule_days_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_schedule_days_office_id ON public.provider_schedule_days USING btree (office_id);


--
-- Name: ix_provider_schedule_days_provider_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_schedule_days_provider_id ON public.provider_schedule_days USING btree (provider_id);


--
-- Name: ix_provider_schedule_days_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_schedule_days_tenant_id ON public.provider_schedule_days USING btree (tenant_id);


--
-- Name: ix_provider_signatures_provider_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_signatures_provider_id ON public.provider_signatures USING btree (provider_id);


--
-- Name: ix_provider_signatures_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_signatures_tenant_id ON public.provider_signatures USING btree (tenant_id);


--
-- Name: ix_provider_watermarks_provider_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_watermarks_provider_id ON public.provider_watermarks USING btree (provider_id);


--
-- Name: ix_provider_watermarks_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provider_watermarks_tenant_id ON public.provider_watermarks USING btree (tenant_id);


--
-- Name: ix_providers_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_providers_user_id ON public.providers USING btree (user_id);


--
-- Name: ix_responsible_parties_legacy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_responsible_parties_legacy_id ON public.responsible_parties USING btree (legacy_id);


--
-- Name: ix_responsible_parties_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_responsible_parties_tenant_id ON public.responsible_parties USING btree (tenant_id);


--
-- Name: ix_signature_audit_events_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_signature_audit_events_entity ON public.signature_audit_events USING btree (entity_type, entity_id);


--
-- Name: ix_signature_audit_events_event; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_signature_audit_events_event ON public.signature_audit_events USING btree (event);


--
-- Name: ix_signature_audit_events_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_signature_audit_events_patient_id ON public.signature_audit_events USING btree (patient_id);


--
-- Name: ix_signature_audit_events_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_signature_audit_events_tenant_id ON public.signature_audit_events USING btree (tenant_id);


--
-- Name: ix_sms_messages_from_phone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sms_messages_from_phone ON public.sms_messages USING btree (from_phone);


--
-- Name: ix_sms_messages_office_sent_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sms_messages_office_sent_at ON public.sms_messages USING btree (office_id, sent_at);


--
-- Name: ix_sms_messages_sent_phone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sms_messages_sent_phone ON public.sms_messages USING btree (sent_phone);


--
-- Name: ix_sms_templates_office_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sms_templates_office_id ON public.sms_templates USING btree (office_id);


--
-- Name: ix_sms_templates_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sms_templates_tenant_id ON public.sms_templates USING btree (tenant_id);


--
-- Name: ix_stored_objects_sha256; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_stored_objects_sha256 ON public.stored_objects USING btree (sha256);


--
-- Name: ix_stored_objects_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_stored_objects_tenant_id ON public.stored_objects USING btree (tenant_id);


--
-- Name: ix_support_tickets_jira_issue_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_support_tickets_jira_issue_key ON public.support_tickets USING btree (jira_issue_key);


--
-- Name: ix_support_tickets_reporter_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_support_tickets_reporter_user_id ON public.support_tickets USING btree (reporter_user_id);


--
-- Name: ix_support_tickets_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_support_tickets_tenant_id ON public.support_tickets USING btree (tenant_id);


--
-- Name: ix_time_clock_entries_tenant_clock_in; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_time_clock_entries_tenant_clock_in ON public.time_clock_entries USING btree (tenant_id, clock_in);


--
-- Name: ix_time_clock_entry_edits_entry_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_time_clock_entry_edits_entry_id ON public.time_clock_entry_edits USING btree (entry_id);


--
-- Name: ix_time_clock_entry_edits_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_time_clock_entry_edits_tenant_id ON public.time_clock_entry_edits USING btree (tenant_id);


--
-- Name: ix_time_clock_periods_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_time_clock_periods_tenant_id ON public.time_clock_periods USING btree (tenant_id);


--
-- Name: ix_tp_insurance_details_ins_plan_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tp_insurance_details_ins_plan_id ON public.treatment_plan_insurance_details USING btree (ins_plan_id);


--
-- Name: ix_treatment_plan_item_icd_codes_icd_code_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_treatment_plan_item_icd_codes_icd_code_id ON public.treatment_plan_item_icd_codes USING btree (icd_code_id);


--
-- Name: ix_treatment_plan_item_icd_codes_plan_item_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_treatment_plan_item_icd_codes_plan_item_id ON public.treatment_plan_item_icd_codes USING btree (plan_item_id);


--
-- Name: ix_user_group_memberships_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_group_memberships_group_id ON public.user_group_memberships USING btree (group_id);


--
-- Name: ix_user_group_memberships_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_group_memberships_tenant_id ON public.user_group_memberships USING btree (tenant_id);


--
-- Name: ix_user_group_memberships_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_group_memberships_user_id ON public.user_group_memberships USING btree (user_id);


--
-- Name: ix_user_group_rights_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_group_rights_group_id ON public.user_group_rights USING btree (group_id);


--
-- Name: ix_user_group_rights_permission_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_group_rights_permission_id ON public.user_group_rights USING btree (permission_id);


--
-- Name: ix_user_group_rights_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_group_rights_tenant_id ON public.user_group_rights USING btree (tenant_id);


--
-- Name: ix_user_groups_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_groups_tenant_id ON public.user_groups USING btree (tenant_id);


--
-- Name: ix_user_ip_rules_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_ip_rules_tenant_id ON public.user_ip_rules USING btree (tenant_id);


--
-- Name: ix_user_ip_rules_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_ip_rules_user_id ON public.user_ip_rules USING btree (user_id);


--
-- Name: ix_user_login_restrictions_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_login_restrictions_tenant_id ON public.user_login_restrictions USING btree (tenant_id);


--
-- Name: ix_user_login_restrictions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_login_restrictions_user_id ON public.user_login_restrictions USING btree (user_id);


--
-- Name: ix_user_preferences_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_preferences_tenant_id ON public.user_preferences USING btree (tenant_id);


--
-- Name: ix_user_preferences_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_preferences_user_id ON public.user_preferences USING btree (user_id);


--
-- Name: ix_user_presence_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_presence_tenant_status ON public.user_presence USING btree (tenant_id, status);


--
-- Name: ix_user_tasks_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_tasks_tenant_id ON public.user_tasks USING btree (tenant_id);


--
-- Name: ix_user_tasks_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_tasks_user_id ON public.user_tasks USING btree (user_id);


--
-- Name: ix_user_time_clock_config_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_time_clock_config_tenant_id ON public.user_time_clock_config USING btree (tenant_id);


--
-- Name: ix_user_time_clock_config_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_time_clock_config_user_id ON public.user_time_clock_config USING btree (user_id);


--
-- Name: ix_users_short_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_short_id ON public.users USING btree (short_id);


--
-- Name: ix_utility_runs_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_utility_runs_tenant_id ON public.utility_runs USING btree (tenant_id);


--
-- Name: ix_utility_runs_utility_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_utility_runs_utility_id ON public.utility_runs USING btree (utility_id);


--
-- Name: uq_fee_schedule_assignments_target; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_fee_schedule_assignments_target ON public.fee_schedule_assignments USING btree (tenant_id, COALESCE(ins_plan_id, 0), COALESCE(carrier_id, 0), COALESCE(provider_id, ''::character varying), COALESCE(specialty_id, ''::character varying), COALESCE(office_id, 0), COALESCE(office_group_id, 0)) WHERE ((ins_plan_id IS NOT NULL) OR (carrier_id IS NOT NULL) OR (provider_id IS NOT NULL) OR (specialty_id IS NOT NULL));


--
-- Name: uq_sms_messages_reminder_dedupe; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_sms_messages_reminder_dedupe ON public.sms_messages USING btree (appointment_id, message_type, reminder_lead_hours) WHERE (reminder_lead_hours IS NOT NULL);


--
-- Name: uq_time_clock_entries_open_shift; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_time_clock_entries_open_shift ON public.time_clock_entries USING btree (tenant_id, user_id) WHERE ((clock_out IS NULL) AND is_active AND (NOT auto_closed));


--
-- Name: uq_time_clock_settings_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_time_clock_settings_tenant ON public.time_clock_settings USING btree (tenant_id);


--
-- Name: account_notes account_notes_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_notes
    ADD CONSTRAINT account_notes_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: account_notes account_notes_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_notes
    ADD CONSTRAINT account_notes_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: appointment_procedures appointment_procedures_appointment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointment_procedures
    ADD CONSTRAINT appointment_procedures_appointment_id_fkey FOREIGN KEY (appointment_id) REFERENCES public.appointments(id);


--
-- Name: appointment_procedures appointment_procedures_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointment_procedures
    ADD CONSTRAINT appointment_procedures_material_id_fkey FOREIGN KEY (material_id) REFERENCES public.chart_materials(id);


--
-- Name: appointment_procedures appointment_procedures_procedure_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointment_procedures
    ADD CONSTRAINT appointment_procedures_procedure_code_fkey FOREIGN KEY (procedure_code) REFERENCES public.procedure_codes(code);


--
-- Name: appointment_procedures appointment_procedures_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointment_procedures
    ADD CONSTRAINT appointment_procedures_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: appointment_procedures appointment_procedures_treatment_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointment_procedures
    ADD CONSTRAINT appointment_procedures_treatment_plan_id_fkey FOREIGN KEY (treatment_plan_id) REFERENCES public.treatment_plans(id);


--
-- Name: appointments appointments_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT appointments_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: appointments appointments_operatory_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT appointments_operatory_id_fkey FOREIGN KEY (operatory_id) REFERENCES public.operatories(id);


--
-- Name: appointments appointments_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT appointments_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: appointments appointments_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT appointments_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: appointments appointments_treatment_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT appointments_treatment_plan_id_fkey FOREIGN KEY (treatment_plan_id) REFERENCES public.treatment_plans(id);


--
-- Name: caries_risk_assessments caries_risk_assessments_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.caries_risk_assessments
    ADD CONSTRAINT caries_risk_assessments_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: caries_risk_assessments caries_risk_assessments_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.caries_risk_assessments
    ADD CONSTRAINT caries_risk_assessments_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: caries_risk_assessments caries_risk_assessments_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.caries_risk_assessments
    ADD CONSTRAINT caries_risk_assessments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: chart_colors chart_colors_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_colors
    ADD CONSTRAINT chart_colors_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: chart_conditions chart_conditions_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_conditions
    ADD CONSTRAINT chart_conditions_material_id_fkey FOREIGN KEY (material_id) REFERENCES public.chart_materials(id);


--
-- Name: chart_conditions chart_conditions_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_conditions
    ADD CONSTRAINT chart_conditions_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: chart_conditions chart_conditions_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_conditions
    ADD CONSTRAINT chart_conditions_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: chart_conditions chart_conditions_procedure_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_conditions
    ADD CONSTRAINT chart_conditions_procedure_code_fkey FOREIGN KEY (procedure_code) REFERENCES public.procedure_codes(code);


--
-- Name: chart_conditions chart_conditions_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_conditions
    ADD CONSTRAINT chart_conditions_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: chart_materials chart_materials_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_materials
    ADD CONSTRAINT chart_materials_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: claim_submissions claim_submissions_claim_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim_submissions
    ADD CONSTRAINT claim_submissions_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES public.insurance_claims(id);


--
-- Name: claim_submissions claim_submissions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim_submissions
    ADD CONSTRAINT claim_submissions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: code_bundle_items code_bundle_items_bundle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_bundle_items
    ADD CONSTRAINT code_bundle_items_bundle_id_fkey FOREIGN KEY (bundle_id) REFERENCES public.code_bundles(id);


--
-- Name: code_bundle_items code_bundle_items_procedure_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_bundle_items
    ADD CONSTRAINT code_bundle_items_procedure_code_fkey FOREIGN KEY (procedure_code) REFERENCES public.procedure_codes(code);


--
-- Name: code_bundles code_bundles_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_bundles
    ADD CONSTRAINT code_bundles_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: code_bundles code_bundles_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_bundles
    ADD CONSTRAINT code_bundles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: codes_view codes_view_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.codes_view
    ADD CONSTRAINT codes_view_code_fkey FOREIGN KEY (code) REFERENCES public.procedure_codes(code);


--
-- Name: codes_view codes_view_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.codes_view
    ADD CONSTRAINT codes_view_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: codes_view codes_view_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.codes_view
    ADD CONSTRAINT codes_view_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: collection_agencies collection_agencies_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_agencies
    ADD CONSTRAINT collection_agencies_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: definition_groups definition_groups_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.definition_groups
    ADD CONSTRAINT definition_groups_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: definitions definitions_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.definitions
    ADD CONSTRAINT definitions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: eligibility_checks eligibility_checks_carrier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eligibility_checks
    ADD CONSTRAINT eligibility_checks_carrier_id_fkey FOREIGN KEY (carrier_id) REFERENCES public.insurance_carriers(id);


--
-- Name: eligibility_checks eligibility_checks_ins_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eligibility_checks
    ADD CONSTRAINT eligibility_checks_ins_plan_id_fkey FOREIGN KEY (ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: eligibility_checks eligibility_checks_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eligibility_checks
    ADD CONSTRAINT eligibility_checks_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: eligibility_checks eligibility_checks_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eligibility_checks
    ADD CONSTRAINT eligibility_checks_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: eligibility_checks eligibility_checks_requested_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eligibility_checks
    ADD CONSTRAINT eligibility_checks_requested_by_fkey FOREIGN KEY (requested_by) REFERENCES public.users(id);


--
-- Name: eligibility_checks eligibility_checks_subscriber_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eligibility_checks
    ADD CONSTRAINT eligibility_checks_subscriber_id_fkey FOREIGN KEY (subscriber_id) REFERENCES public.insurance_subscribers(id);


--
-- Name: eligibility_checks eligibility_checks_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eligibility_checks
    ADD CONSTRAINT eligibility_checks_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: employers employers_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employers
    ADD CONSTRAINT employers_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: fee_schedule_assignments fee_schedule_assignments_carrier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_assignments
    ADD CONSTRAINT fee_schedule_assignments_carrier_id_fkey FOREIGN KEY (carrier_id) REFERENCES public.insurance_carriers(id);


--
-- Name: fee_schedule_assignments fee_schedule_assignments_fee_schedule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_assignments
    ADD CONSTRAINT fee_schedule_assignments_fee_schedule_id_fkey FOREIGN KEY (fee_schedule_id) REFERENCES public.fee_schedules(id);


--
-- Name: fee_schedule_assignments fee_schedule_assignments_ins_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_assignments
    ADD CONSTRAINT fee_schedule_assignments_ins_plan_id_fkey FOREIGN KEY (ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: fee_schedule_assignments fee_schedule_assignments_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_assignments
    ADD CONSTRAINT fee_schedule_assignments_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: fee_schedule_assignments fee_schedule_assignments_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_assignments
    ADD CONSTRAINT fee_schedule_assignments_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: fee_schedule_assignments fee_schedule_assignments_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_assignments
    ADD CONSTRAINT fee_schedule_assignments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: fee_schedule_entries fee_schedule_entries_fee_schedule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_entries
    ADD CONSTRAINT fee_schedule_entries_fee_schedule_id_fkey FOREIGN KEY (fee_schedule_id) REFERENCES public.fee_schedules(id);


--
-- Name: fee_schedule_entries fee_schedule_entries_procedure_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_entries
    ADD CONSTRAINT fee_schedule_entries_procedure_code_fkey FOREIGN KEY (procedure_code) REFERENCES public.procedure_codes(code);


--
-- Name: fee_schedules fee_schedules_ins_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedules
    ADD CONSTRAINT fee_schedules_ins_plan_id_fkey FOREIGN KEY (ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: fee_schedules fee_schedules_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedules
    ADD CONSTRAINT fee_schedules_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: fee_schedules fee_schedules_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedules
    ADD CONSTRAINT fee_schedules_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: account_communications fk_account_communications_sms_reminder_template_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_communications
    ADD CONSTRAINT fk_account_communications_sms_reminder_template_id FOREIGN KEY (sms_reminder_template_id) REFERENCES public.sms_templates(id);


--
-- Name: account_communications fk_account_communications_telecom_verified_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_communications
    ADD CONSTRAINT fk_account_communications_telecom_verified_by_users FOREIGN KEY (telecom_verified_by) REFERENCES public.users(id);


--
-- Name: account_communications fk_account_communications_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_communications
    ADD CONSTRAINT fk_account_communications_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: account_communications fk_account_communications_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_communications
    ADD CONSTRAINT fk_account_communications_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: account_consents fk_account_consents_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_consents
    ADD CONSTRAINT fk_account_consents_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: account_consents fk_account_consents_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_consents
    ADD CONSTRAINT fk_account_consents_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: account_holidays fk_account_holidays_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_holidays
    ADD CONSTRAINT fk_account_holidays_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: account_holidays fk_account_holidays_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_holidays
    ADD CONSTRAINT fk_account_holidays_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: account_holidays fk_account_holidays_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_holidays
    ADD CONSTRAINT fk_account_holidays_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: account_settings fk_account_settings_model_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_settings
    ADD CONSTRAINT fk_account_settings_model_office_id_offices FOREIGN KEY (model_office_id) REFERENCES public.offices(id);


--
-- Name: account_settings fk_account_settings_ortho_visit_code_procedure_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_settings
    ADD CONSTRAINT fk_account_settings_ortho_visit_code_procedure_codes FOREIGN KEY (ortho_visit_code) REFERENCES public.procedure_codes(code);


--
-- Name: account_settings fk_account_settings_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_settings
    ADD CONSTRAINT fk_account_settings_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: account_settings fk_account_settings_transworld_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_settings
    ADD CONSTRAINT fk_account_settings_transworld_office_id_offices FOREIGN KEY (transworld_office_id) REFERENCES public.offices(id);


--
-- Name: account_settings fk_account_settings_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.account_settings
    ADD CONSTRAINT fk_account_settings_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: appointment_procedures fk_appointment_procedures_treatment_plan_item_id_treatm_a582; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointment_procedures
    ADD CONSTRAINT fk_appointment_procedures_treatment_plan_item_id_treatm_a582 FOREIGN KEY (treatment_plan_item_id) REFERENCES public.treatment_plan_items(id);


--
-- Name: appointments fk_appointments_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT fk_appointments_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: appointments fk_appointments_lab_vendor_id_labs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT fk_appointments_lab_vendor_id_labs FOREIGN KEY (lab_vendor_id) REFERENCES public.labs(id);


--
-- Name: appointments fk_appointments_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT fk_appointments_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: appointnow_reasons fk_appointnow_reasons_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointnow_reasons
    ADD CONSTRAINT fk_appointnow_reasons_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: appointnow_reasons fk_appointnow_reasons_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointnow_reasons
    ADD CONSTRAINT fk_appointnow_reasons_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: appointnow_reasons fk_appointnow_reasons_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointnow_reasons
    ADD CONSTRAINT fk_appointnow_reasons_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: auth_action_tokens fk_auth_action_tokens_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_action_tokens
    ADD CONSTRAINT fk_auth_action_tokens_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: booking_requests fk_booking_requests_actioned_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests
    ADD CONSTRAINT fk_booking_requests_actioned_by_users FOREIGN KEY (actioned_by) REFERENCES public.users(id);


--
-- Name: booking_requests fk_booking_requests_appointment_id_appointments; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests
    ADD CONSTRAINT fk_booking_requests_appointment_id_appointments FOREIGN KEY (appointment_id) REFERENCES public.appointments(id);


--
-- Name: booking_requests fk_booking_requests_ledger_payment_id_patient_payments; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests
    ADD CONSTRAINT fk_booking_requests_ledger_payment_id_patient_payments FOREIGN KEY (ledger_payment_id) REFERENCES public.patient_payments(id);


--
-- Name: booking_requests fk_booking_requests_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests
    ADD CONSTRAINT fk_booking_requests_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: booking_requests fk_booking_requests_operatory_id_operatories; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests
    ADD CONSTRAINT fk_booking_requests_operatory_id_operatories FOREIGN KEY (operatory_id) REFERENCES public.operatories(id);


--
-- Name: booking_requests fk_booking_requests_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests
    ADD CONSTRAINT fk_booking_requests_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: booking_requests fk_booking_requests_payment_requested_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests
    ADD CONSTRAINT fk_booking_requests_payment_requested_by_users FOREIGN KEY (payment_requested_by) REFERENCES public.users(id);


--
-- Name: booking_requests fk_booking_requests_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests
    ADD CONSTRAINT fk_booking_requests_provider_id_providers FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: booking_requests fk_booking_requests_refunded_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests
    ADD CONSTRAINT fk_booking_requests_refunded_by_users FOREIGN KEY (refunded_by) REFERENCES public.users(id);


--
-- Name: booking_requests fk_booking_requests_rescheduled_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests
    ADD CONSTRAINT fk_booking_requests_rescheduled_by_users FOREIGN KEY (rescheduled_by) REFERENCES public.users(id);


--
-- Name: booking_requests fk_booking_requests_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests
    ADD CONSTRAINT fk_booking_requests_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: campaigns fk_campaigns_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT fk_campaigns_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: campaigns fk_campaigns_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT fk_campaigns_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: campaigns fk_campaigns_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT fk_campaigns_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: chart_colors fk_chart_colors_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_colors
    ADD CONSTRAINT fk_chart_colors_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: chart_conditions fk_chart_conditions_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_conditions
    ADD CONSTRAINT fk_chart_conditions_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: chart_materials fk_chart_materials_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_materials
    ADD CONSTRAINT fk_chart_materials_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: chart_settings fk_chart_settings_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_settings
    ADD CONSTRAINT fk_chart_settings_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: chart_settings fk_chart_settings_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_settings
    ADD CONSTRAINT fk_chart_settings_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: chart_status_templates fk_chart_status_templates_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_status_templates
    ADD CONSTRAINT fk_chart_status_templates_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: chart_status_templates fk_chart_status_templates_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_status_templates
    ADD CONSTRAINT fk_chart_status_templates_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: chart_status_templates fk_chart_status_templates_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_status_templates
    ADD CONSTRAINT fk_chart_status_templates_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: chart_tooth_notes fk_chart_tooth_notes_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_tooth_notes
    ADD CONSTRAINT fk_chart_tooth_notes_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: chart_tooth_notes fk_chart_tooth_notes_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_tooth_notes
    ADD CONSTRAINT fk_chart_tooth_notes_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: claim_attachments fk_claim_attachments_claim_id_insurance_claims; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim_attachments
    ADD CONSTRAINT fk_claim_attachments_claim_id_insurance_claims FOREIGN KEY (claim_id) REFERENCES public.insurance_claims(id);


--
-- Name: claim_attachments fk_claim_attachments_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim_attachments
    ADD CONSTRAINT fk_claim_attachments_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: claim_attachments fk_claim_attachments_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim_attachments
    ADD CONSTRAINT fk_claim_attachments_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: consent_signatures fk_consent_signatures_consent_id_patient_consents; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.consent_signatures
    ADD CONSTRAINT fk_consent_signatures_consent_id_patient_consents FOREIGN KEY (consent_id) REFERENCES public.patient_consents(id);


--
-- Name: consent_signatures fk_consent_signatures_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.consent_signatures
    ADD CONSTRAINT fk_consent_signatures_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: consent_signatures fk_consent_signatures_signer_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.consent_signatures
    ADD CONSTRAINT fk_consent_signatures_signer_provider_id_providers FOREIGN KEY (signer_provider_id) REFERENCES public.providers(id);


--
-- Name: consent_signatures fk_consent_signatures_signer_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.consent_signatures
    ADD CONSTRAINT fk_consent_signatures_signer_user_id_users FOREIGN KEY (signer_user_id) REFERENCES public.users(id);


--
-- Name: consent_signatures fk_consent_signatures_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.consent_signatures
    ADD CONSTRAINT fk_consent_signatures_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: consent_signatures fk_consent_signatures_voided_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.consent_signatures
    ADD CONSTRAINT fk_consent_signatures_voided_by_users FOREIGN KEY (voided_by) REFERENCES public.users(id);


--
-- Name: conversations fk_conversations_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT fk_conversations_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: conversations fk_conversations_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT fk_conversations_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: conversation_participants fk_cp_conversation_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_participants
    ADD CONSTRAINT fk_cp_conversation_id FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: conversation_participants fk_cp_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_participants
    ADD CONSTRAINT fk_cp_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: conversation_participants fk_cp_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_participants
    ADD CONSTRAINT fk_cp_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: definition_groups fk_definition_groups_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.definition_groups
    ADD CONSTRAINT fk_definition_groups_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: definitions fk_definitions_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.definitions
    ADD CONSTRAINT fk_definitions_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: dicom_instances fk_dicom_instances_original_object_id_stored_objects; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_instances
    ADD CONSTRAINT fk_dicom_instances_original_object_id_stored_objects FOREIGN KEY (original_object_id) REFERENCES public.stored_objects(id);


--
-- Name: dicom_instances fk_dicom_instances_series_id_dicom_series; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_instances
    ADD CONSTRAINT fk_dicom_instances_series_id_dicom_series FOREIGN KEY (series_id) REFERENCES public.dicom_series(id);


--
-- Name: dicom_instances fk_dicom_instances_superseded_by_dicom_instances; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_instances
    ADD CONSTRAINT fk_dicom_instances_superseded_by_dicom_instances FOREIGN KEY (superseded_by) REFERENCES public.dicom_instances(id);


--
-- Name: dicom_instances fk_dicom_instances_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_instances
    ADD CONSTRAINT fk_dicom_instances_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: dicom_instances fk_dicom_instances_thumb_object_id_stored_objects; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_instances
    ADD CONSTRAINT fk_dicom_instances_thumb_object_id_stored_objects FOREIGN KEY (thumb_object_id) REFERENCES public.stored_objects(id);


--
-- Name: dicom_instances fk_dicom_instances_web_object_id_stored_objects; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_instances
    ADD CONSTRAINT fk_dicom_instances_web_object_id_stored_objects FOREIGN KEY (web_object_id) REFERENCES public.stored_objects(id);


--
-- Name: dicom_series fk_dicom_series_study_id_dicom_studies; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_series
    ADD CONSTRAINT fk_dicom_series_study_id_dicom_studies FOREIGN KEY (study_id) REFERENCES public.dicom_studies(id);


--
-- Name: dicom_series fk_dicom_series_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_series
    ADD CONSTRAINT fk_dicom_series_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: dicom_studies fk_dicom_studies_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_studies
    ADD CONSTRAINT fk_dicom_studies_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: dicom_studies fk_dicom_studies_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dicom_studies
    ADD CONSTRAINT fk_dicom_studies_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: email_messages fk_email_messages_appointment_id_appointments; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_messages
    ADD CONSTRAINT fk_email_messages_appointment_id_appointments FOREIGN KEY (appointment_id) REFERENCES public.appointments(id);


--
-- Name: email_messages fk_email_messages_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_messages
    ADD CONSTRAINT fk_email_messages_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: email_messages fk_email_messages_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_messages
    ADD CONSTRAINT fk_email_messages_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: email_messages fk_email_messages_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_messages
    ADD CONSTRAINT fk_email_messages_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: email_messages fk_email_messages_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_messages
    ADD CONSTRAINT fk_email_messages_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: employers fk_employers_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employers
    ADD CONSTRAINT fk_employers_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: employers fk_employers_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employers
    ADD CONSTRAINT fk_employers_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: explosion_code_items fk_explosion_code_items_explosion_code_id_explosion_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.explosion_code_items
    ADD CONSTRAINT fk_explosion_code_items_explosion_code_id_explosion_codes FOREIGN KEY (explosion_code_id) REFERENCES public.explosion_codes(id);


--
-- Name: explosion_code_items fk_explosion_code_items_procedure_code_procedure_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.explosion_code_items
    ADD CONSTRAINT fk_explosion_code_items_procedure_code_procedure_codes FOREIGN KEY (procedure_code) REFERENCES public.procedure_codes(code);


--
-- Name: explosion_codes fk_explosion_codes_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.explosion_codes
    ADD CONSTRAINT fk_explosion_codes_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: explosion_codes fk_explosion_codes_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.explosion_codes
    ADD CONSTRAINT fk_explosion_codes_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: explosion_codes fk_explosion_codes_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.explosion_codes
    ADD CONSTRAINT fk_explosion_codes_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: fee_schedule_assignments fk_fee_schedule_assignments_office_group_id_office_groups; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_assignments
    ADD CONSTRAINT fk_fee_schedule_assignments_office_group_id_office_groups FOREIGN KEY (office_group_id) REFERENCES public.office_groups(id);


--
-- Name: fee_schedule_assignments fk_fee_schedule_assignments_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_assignments
    ADD CONSTRAINT fk_fee_schedule_assignments_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: fee_schedule_entries fk_fee_schedule_entries_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_entries
    ADD CONSTRAINT fk_fee_schedule_entries_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: fee_schedule_entries fk_fee_schedule_entries_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_entries
    ADD CONSTRAINT fk_fee_schedule_entries_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: fee_schedule_entries fk_fee_schedule_entries_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedule_entries
    ADD CONSTRAINT fk_fee_schedule_entries_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: fee_schedules fk_fee_schedules_parent_schedule_id_fee_schedules; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_schedules
    ADD CONSTRAINT fk_fee_schedules_parent_schedule_id_fee_schedules FOREIGN KEY (parent_schedule_id) REFERENCES public.fee_schedules(id);


--
-- Name: insurance_subscribers fk_ins_sub_patient; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_subscribers
    ADD CONSTRAINT fk_ins_sub_patient FOREIGN KEY (subscriber_patient_id) REFERENCES public.patients(id);


--
-- Name: insurance_carriers fk_insurance_carriers_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_carriers
    ADD CONSTRAINT fk_insurance_carriers_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: insurance_claims fk_insurance_claims_other_ins_plan_id_insurance_plans; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_claims
    ADD CONSTRAINT fk_insurance_claims_other_ins_plan_id_insurance_plans FOREIGN KEY (other_ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: insurance_coverage_rules fk_insurance_coverage_rules_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_coverage_rules
    ADD CONSTRAINT fk_insurance_coverage_rules_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: insurance_coverage_rules fk_insurance_coverage_rules_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_coverage_rules
    ADD CONSTRAINT fk_insurance_coverage_rules_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: insurance_plan_frequency_groups fk_insurance_plan_frequency_groups_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plan_frequency_groups
    ADD CONSTRAINT fk_insurance_plan_frequency_groups_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: insurance_plan_frequency_groups fk_insurance_plan_frequency_groups_ins_plan_id_insurance_plans; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plan_frequency_groups
    ADD CONSTRAINT fk_insurance_plan_frequency_groups_ins_plan_id_insurance_plans FOREIGN KEY (ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: insurance_plan_frequency_groups fk_insurance_plan_frequency_groups_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plan_frequency_groups
    ADD CONSTRAINT fk_insurance_plan_frequency_groups_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: insurance_plan_frequency_groups fk_insurance_plan_frequency_groups_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plan_frequency_groups
    ADD CONSTRAINT fk_insurance_plan_frequency_groups_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: insurance_plans fk_insurance_plans_locked_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plans
    ADD CONSTRAINT fk_insurance_plans_locked_by_users FOREIGN KEY (locked_by) REFERENCES public.users(id);


--
-- Name: insurance_plans fk_insurance_plans_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plans
    ADD CONSTRAINT fk_insurance_plans_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: labs fk_labs_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.labs
    ADD CONSTRAINT fk_labs_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: labs fk_labs_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.labs
    ADD CONSTRAINT fk_labs_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: labs fk_labs_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.labs
    ADD CONSTRAINT fk_labs_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: labs fk_labs_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.labs
    ADD CONSTRAINT fk_labs_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: ledger_insurance_details fk_ledger_insurance_details_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ledger_insurance_details
    ADD CONSTRAINT fk_ledger_insurance_details_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: ledger_insurance_details fk_ledger_insurance_details_voided_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ledger_insurance_details
    ADD CONSTRAINT fk_ledger_insurance_details_voided_by_users FOREIGN KEY (voided_by) REFERENCES public.users(id);


--
-- Name: letter_batch_items fk_letter_batch_items_batch_id_letter_batch_runs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_batch_items
    ADD CONSTRAINT fk_letter_batch_items_batch_id_letter_batch_runs FOREIGN KEY (batch_id) REFERENCES public.letter_batch_runs(id);


--
-- Name: letter_batch_items fk_letter_batch_items_document_id_patient_documents; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_batch_items
    ADD CONSTRAINT fk_letter_batch_items_document_id_patient_documents FOREIGN KEY (document_id) REFERENCES public.patient_documents(id);


--
-- Name: letter_batch_items fk_letter_batch_items_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_batch_items
    ADD CONSTRAINT fk_letter_batch_items_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: letter_batch_runs fk_letter_batch_runs_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_batch_runs
    ADD CONSTRAINT fk_letter_batch_runs_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: letter_batch_runs fk_letter_batch_runs_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_batch_runs
    ADD CONSTRAINT fk_letter_batch_runs_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: letter_batch_runs fk_letter_batch_runs_template_id_letter_templates; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_batch_runs
    ADD CONSTRAINT fk_letter_batch_runs_template_id_letter_templates FOREIGN KEY (template_id) REFERENCES public.letter_templates(id);


--
-- Name: letter_batch_runs fk_letter_batch_runs_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_batch_runs
    ADD CONSTRAINT fk_letter_batch_runs_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: message_attachments fk_ma_message_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_attachments
    ADD CONSTRAINT fk_ma_message_id FOREIGN KEY (message_id) REFERENCES public.messages(id) ON DELETE CASCADE;


--
-- Name: message_attachments fk_ma_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_attachments
    ADD CONSTRAINT fk_ma_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: message_attachments fk_ma_uploader_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_attachments
    ADD CONSTRAINT fk_ma_uploader_id_users FOREIGN KEY (uploader_id) REFERENCES public.users(id);


--
-- Name: medical_history_records fk_medical_history_records_completed_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_history_records
    ADD CONSTRAINT fk_medical_history_records_completed_by_users FOREIGN KEY (completed_by) REFERENCES public.users(id);


--
-- Name: medical_history_records fk_medical_history_records_source_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_history_records
    ADD CONSTRAINT fk_medical_history_records_source_patient_id_patients FOREIGN KEY (source_patient_id) REFERENCES public.patients(id);


--
-- Name: medical_history_records fk_medical_history_records_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_history_records
    ADD CONSTRAINT fk_medical_history_records_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: medical_history_records fk_medical_history_records_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_history_records
    ADD CONSTRAINT fk_medical_history_records_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: messages fk_messages_conversation_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT fk_messages_conversation_id FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: messages fk_messages_reply_to_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT fk_messages_reply_to_id FOREIGN KEY (reply_to_id) REFERENCES public.messages(id) ON DELETE SET NULL;


--
-- Name: messages fk_messages_sender_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT fk_messages_sender_id_users FOREIGN KEY (sender_id) REFERENCES public.users(id);


--
-- Name: messages fk_messages_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT fk_messages_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: message_receipts fk_mr_message_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_receipts
    ADD CONSTRAINT fk_mr_message_id FOREIGN KEY (message_id) REFERENCES public.messages(id) ON DELETE CASCADE;


--
-- Name: message_receipts fk_mr_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_receipts
    ADD CONSTRAINT fk_mr_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: message_receipts fk_mr_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_receipts
    ADD CONSTRAINT fk_mr_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: message_recipient_states fk_mrs_message_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_recipient_states
    ADD CONSTRAINT fk_mrs_message_id FOREIGN KEY (message_id) REFERENCES public.messages(id) ON DELETE CASCADE;


--
-- Name: message_recipient_states fk_mrs_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_recipient_states
    ADD CONSTRAINT fk_mrs_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: message_recipient_states fk_mrs_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_recipient_states
    ADD CONSTRAINT fk_mrs_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: message_reactions fk_mrx_message_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_reactions
    ADD CONSTRAINT fk_mrx_message_id FOREIGN KEY (message_id) REFERENCES public.messages(id) ON DELETE CASCADE;


--
-- Name: message_reactions fk_mrx_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_reactions
    ADD CONSTRAINT fk_mrx_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: message_reactions fk_mrx_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_reactions
    ADD CONSTRAINT fk_mrx_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: note_macros fk_note_macros_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_macros
    ADD CONSTRAINT fk_note_macros_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: notifications fk_notifications_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT fk_notifications_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: notifications fk_notifications_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT fk_notifications_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: office_advanced_settings fk_office_advanced_settings_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_advanced_settings
    ADD CONSTRAINT fk_office_advanced_settings_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: office_advanced_settings fk_office_advanced_settings_preferred_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_advanced_settings
    ADD CONSTRAINT fk_office_advanced_settings_preferred_provider_id_providers FOREIGN KEY (preferred_provider_id) REFERENCES public.providers(id);


--
-- Name: office_advanced_settings fk_office_advanced_settings_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_advanced_settings
    ADD CONSTRAINT fk_office_advanced_settings_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: office_advanced_settings fk_office_advanced_settings_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_advanced_settings
    ADD CONSTRAINT fk_office_advanced_settings_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: office_code_bundles fk_office_code_bundles_bundle_id_code_bundles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_code_bundles
    ADD CONSTRAINT fk_office_code_bundles_bundle_id_code_bundles FOREIGN KEY (bundle_id) REFERENCES public.code_bundles(id);


--
-- Name: office_code_bundles fk_office_code_bundles_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_code_bundles
    ADD CONSTRAINT fk_office_code_bundles_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: office_code_bundles fk_office_code_bundles_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_code_bundles
    ADD CONSTRAINT fk_office_code_bundles_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: office_integrations fk_office_integrations_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_integrations
    ADD CONSTRAINT fk_office_integrations_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: office_integrations fk_office_integrations_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_integrations
    ADD CONSTRAINT fk_office_integrations_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: office_integrations fk_office_integrations_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_integrations
    ADD CONSTRAINT fk_office_integrations_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: office_letter_templates fk_office_letter_templates_letter_template_id_letter_templates; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_letter_templates
    ADD CONSTRAINT fk_office_letter_templates_letter_template_id_letter_templates FOREIGN KEY (letter_template_id) REFERENCES public.letter_templates(id);


--
-- Name: office_letter_templates fk_office_letter_templates_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_letter_templates
    ADD CONSTRAINT fk_office_letter_templates_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: office_letter_templates fk_office_letter_templates_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_letter_templates
    ADD CONSTRAINT fk_office_letter_templates_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: office_note_macros fk_office_note_macros_note_macro_id_note_macros; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_note_macros
    ADD CONSTRAINT fk_office_note_macros_note_macro_id_note_macros FOREIGN KEY (note_macro_id) REFERENCES public.note_macros(id);


--
-- Name: office_note_macros fk_office_note_macros_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_note_macros
    ADD CONSTRAINT fk_office_note_macros_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: office_note_macros fk_office_note_macros_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_note_macros
    ADD CONSTRAINT fk_office_note_macros_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: office_phone_assignments fk_office_phone_assignments_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_phone_assignments
    ADD CONSTRAINT fk_office_phone_assignments_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: office_phone_assignments fk_office_phone_assignments_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_phone_assignments
    ADD CONSTRAINT fk_office_phone_assignments_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: office_prescription_library fk_office_prescription_library_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_prescription_library
    ADD CONSTRAINT fk_office_prescription_library_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: office_prescription_library fk_office_prescription_library_prescription_library_id__43f0; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_prescription_library
    ADD CONSTRAINT fk_office_prescription_library_prescription_library_id__43f0 FOREIGN KEY (prescription_library_id) REFERENCES public.prescription_library(id);


--
-- Name: office_prescription_library fk_office_prescription_library_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_prescription_library
    ADD CONSTRAINT fk_office_prescription_library_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: office_procedure_codes fk_office_procedure_codes_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_procedure_codes
    ADD CONSTRAINT fk_office_procedure_codes_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: office_procedure_codes fk_office_procedure_codes_procedure_code_procedure_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_procedure_codes
    ADD CONSTRAINT fk_office_procedure_codes_procedure_code_procedure_codes FOREIGN KEY (procedure_code) REFERENCES public.procedure_codes(code);


--
-- Name: office_procedure_codes fk_office_procedure_codes_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_procedure_codes
    ADD CONSTRAINT fk_office_procedure_codes_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: office_production_types fk_office_production_types_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_production_types
    ADD CONSTRAINT fk_office_production_types_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: office_production_types fk_office_production_types_production_type_id_production_types; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_production_types
    ADD CONSTRAINT fk_office_production_types_production_type_id_production_types FOREIGN KEY (production_type_id) REFERENCES public.production_types(id);


--
-- Name: office_production_types fk_office_production_types_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_production_types
    ADD CONSTRAINT fk_office_production_types_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: office_schedule_days fk_office_schedule_days_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_schedule_days
    ADD CONSTRAINT fk_office_schedule_days_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: office_schedule_days fk_office_schedule_days_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_schedule_days
    ADD CONSTRAINT fk_office_schedule_days_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: office_smart_assist_items fk_office_smart_assist_items_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_smart_assist_items
    ADD CONSTRAINT fk_office_smart_assist_items_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: office_smart_assist_items fk_office_smart_assist_items_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_smart_assist_items
    ADD CONSTRAINT fk_office_smart_assist_items_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: office_smart_assist fk_office_smart_assist_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_smart_assist
    ADD CONSTRAINT fk_office_smart_assist_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: office_smart_assist fk_office_smart_assist_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_smart_assist
    ADD CONSTRAINT fk_office_smart_assist_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: office_smart_assist fk_office_smart_assist_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_smart_assist
    ADD CONSTRAINT fk_office_smart_assist_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: office_statement_settings fk_office_statement_settings_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_statement_settings
    ADD CONSTRAINT fk_office_statement_settings_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: office_statement_settings fk_office_statement_settings_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_statement_settings
    ADD CONSTRAINT fk_office_statement_settings_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: office_statement_settings fk_office_statement_settings_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_statement_settings
    ADD CONSTRAINT fk_office_statement_settings_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: offices fk_offices_billing_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offices
    ADD CONSTRAINT fk_offices_billing_provider_id_providers FOREIGN KEY (billing_provider_id) REFERENCES public.providers(id);


--
-- Name: offices fk_offices_default_fee_schedule_id_fee_schedules; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offices
    ADD CONSTRAINT fk_offices_default_fee_schedule_id_fee_schedules FOREIGN KEY (default_fee_schedule_id) REFERENCES public.fee_schedules(id);


--
-- Name: offices fk_offices_default_ucr_fee_schedule_id_fee_schedules; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offices
    ADD CONSTRAINT fk_offices_default_ucr_fee_schedule_id_fee_schedules FOREIGN KEY (default_ucr_fee_schedule_id) REFERENCES public.fee_schedules(id);


--
-- Name: offices fk_offices_office_group_id_office_groups; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offices
    ADD CONSTRAINT fk_offices_office_group_id_office_groups FOREIGN KEY (office_group_id) REFERENCES public.office_groups(id);


--
-- Name: operatories fk_operatories_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.operatories
    ADD CONSTRAINT fk_operatories_provider_id_providers FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: ortho_plans fk_ortho_plans_created_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ortho_plans
    ADD CONSTRAINT fk_ortho_plans_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id);


--
-- Name: ortho_plans fk_ortho_plans_created_office; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ortho_plans
    ADD CONSTRAINT fk_ortho_plans_created_office FOREIGN KEY (created_office_id) REFERENCES public.offices(id);


--
-- Name: ortho_plans fk_ortho_plans_initial_procedure_code; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ortho_plans
    ADD CONSTRAINT fk_ortho_plans_initial_procedure_code FOREIGN KEY (initial_procedure_code) REFERENCES public.procedure_codes(code);


--
-- Name: ortho_plans fk_ortho_plans_pref_provider; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ortho_plans
    ADD CONSTRAINT fk_ortho_plans_pref_provider FOREIGN KEY (pref_provider_id) REFERENCES public.providers(id);


--
-- Name: ortho_plans fk_ortho_plans_updated_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ortho_plans
    ADD CONSTRAINT fk_ortho_plans_updated_by FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: patient_adjustments fk_patient_adjustments_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_adjustments
    ADD CONSTRAINT fk_patient_adjustments_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_adjustments fk_patient_adjustments_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_adjustments
    ADD CONSTRAINT fk_patient_adjustments_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: patient_adjustments fk_patient_adjustments_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_adjustments
    ADD CONSTRAINT fk_patient_adjustments_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_adjustments fk_patient_adjustments_procedure_id_patient_procedures; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_adjustments
    ADD CONSTRAINT fk_patient_adjustments_procedure_id_patient_procedures FOREIGN KEY (procedure_id) REFERENCES public.patient_procedures(id);


--
-- Name: patient_adjustments fk_patient_adjustments_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_adjustments
    ADD CONSTRAINT fk_patient_adjustments_provider_id_providers FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: patient_adjustments fk_patient_adjustments_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_adjustments
    ADD CONSTRAINT fk_patient_adjustments_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_alerts fk_patient_alerts_source_medical_alert_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_alerts
    ADD CONSTRAINT fk_patient_alerts_source_medical_alert_id FOREIGN KEY (source_medical_alert_id) REFERENCES public.patient_medical_alerts(id);


--
-- Name: patient_consents fk_patient_consents_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_consents
    ADD CONSTRAINT fk_patient_consents_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_consents fk_patient_consents_document_id_patient_documents; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_consents
    ADD CONSTRAINT fk_patient_consents_document_id_patient_documents FOREIGN KEY (document_id) REFERENCES public.patient_documents(id);


--
-- Name: patient_consents fk_patient_consents_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_consents
    ADD CONSTRAINT fk_patient_consents_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_consents fk_patient_consents_plan_id_treatment_plans; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_consents
    ADD CONSTRAINT fk_patient_consents_plan_id_treatment_plans FOREIGN KEY (plan_id) REFERENCES public.treatment_plans(id);


--
-- Name: patient_consents fk_patient_consents_signed_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_consents
    ADD CONSTRAINT fk_patient_consents_signed_by_users FOREIGN KEY (signed_by) REFERENCES public.users(id);


--
-- Name: patient_consents fk_patient_consents_signed_document_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_consents
    ADD CONSTRAINT fk_patient_consents_signed_document_id FOREIGN KEY (signed_document_id) REFERENCES public.patient_documents(id);


--
-- Name: patient_consents fk_patient_consents_template_id_letter_templates; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_consents
    ADD CONSTRAINT fk_patient_consents_template_id_letter_templates FOREIGN KEY (template_id) REFERENCES public.letter_templates(id);


--
-- Name: patient_consents fk_patient_consents_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_consents
    ADD CONSTRAINT fk_patient_consents_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_documents fk_patient_documents_claim_id_insurance_claims; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_documents
    ADD CONSTRAINT fk_patient_documents_claim_id_insurance_claims FOREIGN KEY (claim_id) REFERENCES public.insurance_claims(id);


--
-- Name: patient_documents fk_patient_documents_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_documents
    ADD CONSTRAINT fk_patient_documents_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_documents fk_patient_documents_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_documents
    ADD CONSTRAINT fk_patient_documents_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: patient_documents fk_patient_documents_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_documents
    ADD CONSTRAINT fk_patient_documents_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_documents fk_patient_documents_procedure_id_patient_procedures; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_documents
    ADD CONSTRAINT fk_patient_documents_procedure_id_patient_procedures FOREIGN KEY (procedure_id) REFERENCES public.patient_procedures(id);


--
-- Name: patient_documents fk_patient_documents_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_documents
    ADD CONSTRAINT fk_patient_documents_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_emergency_contacts fk_patient_emergency_contacts_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_emergency_contacts
    ADD CONSTRAINT fk_patient_emergency_contacts_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_emergency_contacts fk_patient_emergency_contacts_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_emergency_contacts
    ADD CONSTRAINT fk_patient_emergency_contacts_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_emergency_contacts fk_patient_emergency_contacts_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_emergency_contacts
    ADD CONSTRAINT fk_patient_emergency_contacts_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_ins_payment_plans fk_patient_ins_payment_plans_ortho_plan; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_ins_payment_plans
    ADD CONSTRAINT fk_patient_ins_payment_plans_ortho_plan FOREIGN KEY (ortho_plan_id) REFERENCES public.ortho_plans(id);


--
-- Name: patient_medical_alerts fk_patient_medical_alerts_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_alerts
    ADD CONSTRAINT fk_patient_medical_alerts_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_medical_alerts fk_patient_medical_alerts_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_alerts
    ADD CONSTRAINT fk_patient_medical_alerts_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_medical_alerts fk_patient_medical_alerts_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_alerts
    ADD CONSTRAINT fk_patient_medical_alerts_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_medical_alerts fk_patient_medical_alerts_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_alerts
    ADD CONSTRAINT fk_patient_medical_alerts_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: patient_medical_history fk_patient_medical_history_alerts_completed_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history
    ADD CONSTRAINT fk_patient_medical_history_alerts_completed_by_users FOREIGN KEY (alerts_completed_by) REFERENCES public.users(id);


--
-- Name: patient_medical_history fk_patient_medical_history_copied_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history
    ADD CONSTRAINT fk_patient_medical_history_copied_by_users FOREIGN KEY (copied_by) REFERENCES public.users(id);


--
-- Name: patient_medical_history fk_patient_medical_history_copied_from_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history
    ADD CONSTRAINT fk_patient_medical_history_copied_from_patient_id_patients FOREIGN KEY (copied_from_patient_id) REFERENCES public.patients(id);


--
-- Name: patient_medical_history fk_patient_medical_history_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history
    ADD CONSTRAINT fk_patient_medical_history_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_medical_history fk_patient_medical_history_dental_completed_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history
    ADD CONSTRAINT fk_patient_medical_history_dental_completed_by_users FOREIGN KEY (dental_completed_by) REFERENCES public.users(id);


--
-- Name: patient_medical_history_events fk_patient_medical_history_events_changed_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history_events
    ADD CONSTRAINT fk_patient_medical_history_events_changed_by_users FOREIGN KEY (changed_by) REFERENCES public.users(id);


--
-- Name: patient_medical_history_events fk_patient_medical_history_events_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history_events
    ADD CONSTRAINT fk_patient_medical_history_events_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_medical_history_events fk_patient_medical_history_events_source_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history_events
    ADD CONSTRAINT fk_patient_medical_history_events_source_patient_id_patients FOREIGN KEY (source_patient_id) REFERENCES public.patients(id);


--
-- Name: patient_medical_history_events fk_patient_medical_history_events_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history_events
    ADD CONSTRAINT fk_patient_medical_history_events_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_medical_history fk_patient_medical_history_last_signature_id_patient_signatures; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history
    ADD CONSTRAINT fk_patient_medical_history_last_signature_id_patient_signatures FOREIGN KEY (last_signature_id) REFERENCES public.patient_signatures(id);


--
-- Name: patient_medical_history fk_patient_medical_history_last_version_id_medical_hist_e228; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history
    ADD CONSTRAINT fk_patient_medical_history_last_version_id_medical_hist_e228 FOREIGN KEY (last_version_id) REFERENCES public.medical_history_records(id);


--
-- Name: patient_medical_history fk_patient_medical_history_medical_completed_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history
    ADD CONSTRAINT fk_patient_medical_history_medical_completed_by_users FOREIGN KEY (medical_completed_by) REFERENCES public.users(id);


--
-- Name: patient_medical_history fk_patient_medical_history_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history
    ADD CONSTRAINT fk_patient_medical_history_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_medical_history fk_patient_medical_history_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history
    ADD CONSTRAINT fk_patient_medical_history_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_medical_history fk_patient_medical_history_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medical_history
    ADD CONSTRAINT fk_patient_medical_history_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: patient_notes fk_patient_notes_document_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_notes
    ADD CONSTRAINT fk_patient_notes_document_id FOREIGN KEY (document_id) REFERENCES public.patient_documents(id);


--
-- Name: patient_notes fk_patient_notes_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_notes
    ADD CONSTRAINT fk_patient_notes_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: patient_opening_balances fk_patient_opening_balances_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_opening_balances
    ADD CONSTRAINT fk_patient_opening_balances_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_opening_balances fk_patient_opening_balances_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_opening_balances
    ADD CONSTRAINT fk_patient_opening_balances_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_opening_balances fk_patient_opening_balances_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_opening_balances
    ADD CONSTRAINT fk_patient_opening_balances_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_payment_plans fk_patient_payment_plans_created_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payment_plans
    ADD CONSTRAINT fk_patient_payment_plans_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id);


--
-- Name: patient_payment_plans fk_patient_payment_plans_treatment_plan; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payment_plans
    ADD CONSTRAINT fk_patient_payment_plans_treatment_plan FOREIGN KEY (treatment_plan_id) REFERENCES public.treatment_plans(id);


--
-- Name: patient_payment_plans fk_patient_payment_plans_updated_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payment_plans
    ADD CONSTRAINT fk_patient_payment_plans_updated_by FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: patient_payments fk_patient_payments_created_office; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payments
    ADD CONSTRAINT fk_patient_payments_created_office FOREIGN KEY (created_office_id) REFERENCES public.offices(id) ON DELETE SET NULL;


--
-- Name: patient_payments fk_patient_payments_updated_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payments
    ADD CONSTRAINT fk_patient_payments_updated_by FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: patient_plan_installments fk_patient_plan_installments_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_plan_installments
    ADD CONSTRAINT fk_patient_plan_installments_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_plan_installments fk_patient_plan_installments_ortho_plan_id_ortho_plans; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_plan_installments
    ADD CONSTRAINT fk_patient_plan_installments_ortho_plan_id_ortho_plans FOREIGN KEY (ortho_plan_id) REFERENCES public.ortho_plans(id);


--
-- Name: patient_plan_installments fk_patient_plan_installments_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_plan_installments
    ADD CONSTRAINT fk_patient_plan_installments_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_plan_installments fk_patient_plan_installments_payment_plan_id_patient_pa_a2d7; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_plan_installments
    ADD CONSTRAINT fk_patient_plan_installments_payment_plan_id_patient_pa_a2d7 FOREIGN KEY (payment_plan_id) REFERENCES public.patient_payment_plans(id);


--
-- Name: patient_plan_installments fk_patient_plan_installments_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_plan_installments
    ADD CONSTRAINT fk_patient_plan_installments_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_procedures fk_patient_procedures_coverage_rule; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT fk_patient_procedures_coverage_rule FOREIGN KEY (coverage_rule_id) REFERENCES public.insurance_coverage_rules(id);


--
-- Name: patient_procedures fk_patient_procedures_fee_schedule_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT fk_patient_procedures_fee_schedule_id FOREIGN KEY (fee_schedule_id) REFERENCES public.fee_schedules(id);


--
-- Name: patient_procedures fk_patient_procedures_hygienist_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT fk_patient_procedures_hygienist_id_providers FOREIGN KEY (hygienist_id) REFERENCES public.providers(id);


--
-- Name: patient_procedures fk_patient_procedures_treatment_plan_id_treatment_plans; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT fk_patient_procedures_treatment_plan_id_treatment_plans FOREIGN KEY (treatment_plan_id) REFERENCES public.treatment_plans(id);


--
-- Name: patient_procedures fk_patient_procedures_treatment_plan_item_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT fk_patient_procedures_treatment_plan_item_id FOREIGN KEY (treatment_plan_item_id) REFERENCES public.treatment_plan_items(id);


--
-- Name: patient_procedures fk_patient_procedures_updated_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT fk_patient_procedures_updated_by FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: patient_questionnaire_responses fk_patient_questionnaire_responses_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_questionnaire_responses
    ADD CONSTRAINT fk_patient_questionnaire_responses_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_questionnaire_responses fk_patient_questionnaire_responses_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_questionnaire_responses
    ADD CONSTRAINT fk_patient_questionnaire_responses_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_questionnaire_responses fk_patient_questionnaire_responses_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_questionnaire_responses
    ADD CONSTRAINT fk_patient_questionnaire_responses_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_questionnaire_responses fk_patient_questionnaire_responses_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_questionnaire_responses
    ADD CONSTRAINT fk_patient_questionnaire_responses_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: patient_refunds fk_patient_refunds_authorized_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_refunds
    ADD CONSTRAINT fk_patient_refunds_authorized_by_users FOREIGN KEY (authorized_by) REFERENCES public.users(id);


--
-- Name: patient_refunds fk_patient_refunds_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_refunds
    ADD CONSTRAINT fk_patient_refunds_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_refunds fk_patient_refunds_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_refunds
    ADD CONSTRAINT fk_patient_refunds_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: patient_refunds fk_patient_refunds_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_refunds
    ADD CONSTRAINT fk_patient_refunds_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_refunds fk_patient_refunds_source_payment_id_patient_payments; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_refunds
    ADD CONSTRAINT fk_patient_refunds_source_payment_id_patient_payments FOREIGN KEY (source_payment_id) REFERENCES public.patient_payments(id);


--
-- Name: patient_refunds fk_patient_refunds_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_refunds
    ADD CONSTRAINT fk_patient_refunds_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_sec_ins_payment_plans fk_patient_sec_ins_payment_plans_ortho_plan; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_sec_ins_payment_plans
    ADD CONSTRAINT fk_patient_sec_ins_payment_plans_ortho_plan FOREIGN KEY (ortho_plan_id) REFERENCES public.ortho_plans(id);


--
-- Name: patient_signatures fk_patient_signatures_claim_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_signatures
    ADD CONSTRAINT fk_patient_signatures_claim_id FOREIGN KEY (claim_id) REFERENCES public.insurance_claims(id);


--
-- Name: patient_signatures fk_patient_signatures_consent_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_signatures
    ADD CONSTRAINT fk_patient_signatures_consent_id FOREIGN KEY (consent_id) REFERENCES public.patient_consents(id);


--
-- Name: patient_signatures fk_patient_signatures_progress_note_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_signatures
    ADD CONSTRAINT fk_patient_signatures_progress_note_id FOREIGN KEY (progress_note_id) REFERENCES public.progress_notes(id);


--
-- Name: patient_signatures fk_patient_signatures_signed_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_signatures
    ADD CONSTRAINT fk_patient_signatures_signed_by_user_id_users FOREIGN KEY (signed_by_user_id) REFERENCES public.users(id);


--
-- Name: patient_signatures fk_patient_signatures_signer_provider_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_signatures
    ADD CONSTRAINT fk_patient_signatures_signer_provider_id FOREIGN KEY (signer_provider_id) REFERENCES public.providers(id);


--
-- Name: patient_signatures fk_patient_signatures_superseded_by_id_patient_signatures; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_signatures
    ADD CONSTRAINT fk_patient_signatures_superseded_by_id_patient_signatures FOREIGN KEY (superseded_by_id) REFERENCES public.patient_signatures(id);


--
-- Name: patient_signatures fk_patient_signatures_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_signatures
    ADD CONSTRAINT fk_patient_signatures_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: patient_signatures fk_patient_signatures_voided_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_signatures
    ADD CONSTRAINT fk_patient_signatures_voided_by_users FOREIGN KEY (voided_by) REFERENCES public.users(id);


--
-- Name: patient_statements fk_patient_statements_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_statements
    ADD CONSTRAINT fk_patient_statements_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_statements fk_patient_statements_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_statements
    ADD CONSTRAINT fk_patient_statements_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: patient_statements fk_patient_statements_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_statements
    ADD CONSTRAINT fk_patient_statements_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_statements fk_patient_statements_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_statements
    ADD CONSTRAINT fk_patient_statements_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patients fk_patients_fee_schedule_id_fee_schedules; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT fk_patients_fee_schedule_id_fee_schedules FOREIGN KEY (fee_schedule_id) REFERENCES public.fee_schedules(id);


--
-- Name: patients fk_patients_photo_document_id_patient_documents; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT fk_patients_photo_document_id_patient_documents FOREIGN KEY (photo_document_id) REFERENCES public.patient_documents(id);


--
-- Name: patients fk_patients_preferred_hygienist_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT fk_patients_preferred_hygienist_id_providers FOREIGN KEY (preferred_hygienist_id) REFERENCES public.providers(id);


--
-- Name: patients fk_patients_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT fk_patients_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: payment_allocations fk_payment_allocations_adjustment_id_patient_adjustments; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_allocations
    ADD CONSTRAINT fk_payment_allocations_adjustment_id_patient_adjustments FOREIGN KEY (adjustment_id) REFERENCES public.patient_adjustments(id);


--
-- Name: perio_chart_templates fk_perio_chart_templates_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_chart_templates
    ADD CONSTRAINT fk_perio_chart_templates_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: perio_chart_templates fk_perio_chart_templates_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_chart_templates
    ADD CONSTRAINT fk_perio_chart_templates_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: perio_chart_templates fk_perio_chart_templates_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_chart_templates
    ADD CONSTRAINT fk_perio_chart_templates_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: perio_exam_details fk_perio_exam_details_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_exam_details
    ADD CONSTRAINT fk_perio_exam_details_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: perio_exam_details fk_perio_exam_details_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_exam_details
    ADD CONSTRAINT fk_perio_exam_details_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: perio_exams fk_perio_exams_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_exams
    ADD CONSTRAINT fk_perio_exams_provider_id_providers FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: perio_exams fk_perio_exams_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_exams
    ADD CONSTRAINT fk_perio_exams_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: place_of_service_codes fk_place_of_service_codes_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.place_of_service_codes
    ADD CONSTRAINT fk_place_of_service_codes_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: place_of_service_codes fk_place_of_service_codes_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.place_of_service_codes
    ADD CONSTRAINT fk_place_of_service_codes_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: prescription_library fk_prescription_library_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescription_library
    ADD CONSTRAINT fk_prescription_library_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: prescription_library fk_prescription_library_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescription_library
    ADD CONSTRAINT fk_prescription_library_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: prescriptions fk_prescriptions_alerts_acknowledged_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescriptions
    ADD CONSTRAINT fk_prescriptions_alerts_acknowledged_by_users FOREIGN KEY (alerts_acknowledged_by) REFERENCES public.users(id);


--
-- Name: patient_procedures fk_proc_claim; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT fk_proc_claim FOREIGN KEY (claim_id) REFERENCES public.insurance_claims(id);


--
-- Name: procedure_codes fk_procedure_codes_default_material_id_chart_materials; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_codes
    ADD CONSTRAINT fk_procedure_codes_default_material_id_chart_materials FOREIGN KEY (default_material_id) REFERENCES public.chart_materials(id);


--
-- Name: procedure_codes fk_procedure_codes_default_notes_macro_id_note_macros; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_codes
    ADD CONSTRAINT fk_procedure_codes_default_notes_macro_id_note_macros FOREIGN KEY (default_notes_macro_id) REFERENCES public.note_macros(id);


--
-- Name: procedure_codes fk_procedure_codes_default_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_codes
    ADD CONSTRAINT fk_procedure_codes_default_provider_id_providers FOREIGN KEY (default_provider_id) REFERENCES public.providers(id);


--
-- Name: procedure_fee_provenance fk_procedure_fee_provenance_fee_schedule_id_fee_schedules; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_fee_provenance
    ADD CONSTRAINT fk_procedure_fee_provenance_fee_schedule_id_fee_schedules FOREIGN KEY (fee_schedule_id) REFERENCES public.fee_schedules(id);


--
-- Name: procedure_fee_provenance fk_procedure_fee_provenance_procedure_id_patient_procedures; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_fee_provenance
    ADD CONSTRAINT fk_procedure_fee_provenance_procedure_id_patient_procedures FOREIGN KEY (procedure_id) REFERENCES public.patient_procedures(id);


--
-- Name: procedure_insurance_rules fk_procedure_insurance_rules_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_insurance_rules
    ADD CONSTRAINT fk_procedure_insurance_rules_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: procedure_insurance_rules fk_procedure_insurance_rules_procedure_code_procedure_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_insurance_rules
    ADD CONSTRAINT fk_procedure_insurance_rules_procedure_code_procedure_codes FOREIGN KEY (procedure_code) REFERENCES public.procedure_codes(code);


--
-- Name: procedure_insurance_rules fk_procedure_insurance_rules_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_insurance_rules
    ADD CONSTRAINT fk_procedure_insurance_rules_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: procedure_insurance_rules fk_procedure_insurance_rules_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.procedure_insurance_rules
    ADD CONSTRAINT fk_procedure_insurance_rules_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: production_types fk_production_types_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.production_types
    ADD CONSTRAINT fk_production_types_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: progress_note_attachments fk_progress_note_attachments_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.progress_note_attachments
    ADD CONSTRAINT fk_progress_note_attachments_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: progress_note_attachments fk_progress_note_attachments_progress_note_id_progress_notes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.progress_note_attachments
    ADD CONSTRAINT fk_progress_note_attachments_progress_note_id_progress_notes FOREIGN KEY (progress_note_id) REFERENCES public.progress_notes(id);


--
-- Name: progress_note_attachments fk_progress_note_attachments_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.progress_note_attachments
    ADD CONSTRAINT fk_progress_note_attachments_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: progress_notes fk_progress_notes_drawing_doc_id_patient_documents; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.progress_notes
    ADD CONSTRAINT fk_progress_notes_drawing_doc_id_patient_documents FOREIGN KEY (drawing_doc_id) REFERENCES public.patient_documents(id);


--
-- Name: progress_notes fk_progress_notes_signed_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.progress_notes
    ADD CONSTRAINT fk_progress_notes_signed_by_users FOREIGN KEY (signed_by) REFERENCES public.users(id);


--
-- Name: progress_notes fk_progress_notes_struck_off_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.progress_notes
    ADD CONSTRAINT fk_progress_notes_struck_off_by_users FOREIGN KEY (struck_off_by) REFERENCES public.users(id);


--
-- Name: progress_notes fk_progress_notes_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.progress_notes
    ADD CONSTRAINT fk_progress_notes_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: provider_carrier_logins fk_provider_carrier_logins_carrier_id_insurance_carriers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_carrier_logins
    ADD CONSTRAINT fk_provider_carrier_logins_carrier_id_insurance_carriers FOREIGN KEY (carrier_id) REFERENCES public.insurance_carriers(id);


--
-- Name: provider_carrier_logins fk_provider_carrier_logins_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_carrier_logins
    ADD CONSTRAINT fk_provider_carrier_logins_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: provider_carrier_logins fk_provider_carrier_logins_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_carrier_logins
    ADD CONSTRAINT fk_provider_carrier_logins_provider_id_providers FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: provider_carrier_logins fk_provider_carrier_logins_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_carrier_logins
    ADD CONSTRAINT fk_provider_carrier_logins_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: provider_carrier_logins fk_provider_carrier_logins_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_carrier_logins
    ADD CONSTRAINT fk_provider_carrier_logins_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: provider_holidays fk_provider_holidays_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_holidays
    ADD CONSTRAINT fk_provider_holidays_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: provider_holidays fk_provider_holidays_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_holidays
    ADD CONSTRAINT fk_provider_holidays_provider_id_providers FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: provider_holidays fk_provider_holidays_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_holidays
    ADD CONSTRAINT fk_provider_holidays_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: provider_offices fk_provider_offices_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_offices
    ADD CONSTRAINT fk_provider_offices_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: provider_offices fk_provider_offices_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_offices
    ADD CONSTRAINT fk_provider_offices_provider_id_providers FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: provider_offices fk_provider_offices_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_offices
    ADD CONSTRAINT fk_provider_offices_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: provider_procedure_codes fk_provider_procedure_codes_procedure_code_procedure_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_procedure_codes
    ADD CONSTRAINT fk_provider_procedure_codes_procedure_code_procedure_codes FOREIGN KEY (procedure_code) REFERENCES public.procedure_codes(code);


--
-- Name: provider_procedure_codes fk_provider_procedure_codes_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_procedure_codes
    ADD CONSTRAINT fk_provider_procedure_codes_provider_id_providers FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: provider_procedure_codes fk_provider_procedure_codes_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_procedure_codes
    ADD CONSTRAINT fk_provider_procedure_codes_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: provider_referral_offices fk_provider_referral_offices_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_referral_offices
    ADD CONSTRAINT fk_provider_referral_offices_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: provider_referral_offices fk_provider_referral_offices_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_referral_offices
    ADD CONSTRAINT fk_provider_referral_offices_provider_id_providers FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: provider_referral_offices fk_provider_referral_offices_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_referral_offices
    ADD CONSTRAINT fk_provider_referral_offices_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: provider_schedule_days fk_provider_schedule_days_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_schedule_days
    ADD CONSTRAINT fk_provider_schedule_days_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: provider_schedule_days fk_provider_schedule_days_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_schedule_days
    ADD CONSTRAINT fk_provider_schedule_days_provider_id_providers FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: provider_schedule_days fk_provider_schedule_days_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_schedule_days
    ADD CONSTRAINT fk_provider_schedule_days_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: provider_signatures fk_provider_signatures_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_signatures
    ADD CONSTRAINT fk_provider_signatures_provider_id_providers FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: provider_signatures fk_provider_signatures_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_signatures
    ADD CONSTRAINT fk_provider_signatures_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: provider_signatures fk_provider_signatures_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_signatures
    ADD CONSTRAINT fk_provider_signatures_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: provider_watermarks fk_provider_watermarks_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_watermarks
    ADD CONSTRAINT fk_provider_watermarks_provider_id_providers FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: provider_watermarks fk_provider_watermarks_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_watermarks
    ADD CONSTRAINT fk_provider_watermarks_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: provider_watermarks fk_provider_watermarks_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_watermarks
    ADD CONSTRAINT fk_provider_watermarks_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: providers fk_providers_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT fk_providers_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: providers fk_providers_default_operatory_id_operatories; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT fk_providers_default_operatory_id_operatories FOREIGN KEY (default_operatory_id) REFERENCES public.operatories(id);


--
-- Name: providers fk_providers_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT fk_providers_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: responsible_parties fk_responsible_parties_collection_agency_id_collection_agencies; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.responsible_parties
    ADD CONSTRAINT fk_responsible_parties_collection_agency_id_collection_agencies FOREIGN KEY (collection_agency_id) REFERENCES public.collection_agencies(id);


--
-- Name: responsible_parties fk_responsible_parties_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.responsible_parties
    ADD CONSTRAINT fk_responsible_parties_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: responsible_parties fk_responsible_parties_home_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.responsible_parties
    ADD CONSTRAINT fk_responsible_parties_home_office_id_offices FOREIGN KEY (home_office_id) REFERENCES public.offices(id);


--
-- Name: responsible_parties fk_responsible_parties_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.responsible_parties
    ADD CONSTRAINT fk_responsible_parties_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: signature_audit_events fk_signature_audit_events_actor_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signature_audit_events
    ADD CONSTRAINT fk_signature_audit_events_actor_id_users FOREIGN KEY (actor_id) REFERENCES public.users(id);


--
-- Name: signature_audit_events fk_signature_audit_events_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signature_audit_events
    ADD CONSTRAINT fk_signature_audit_events_patient_id_patients FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: signature_audit_events fk_signature_audit_events_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signature_audit_events
    ADD CONSTRAINT fk_signature_audit_events_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: sms_messages fk_sms_messages_template_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_messages
    ADD CONSTRAINT fk_sms_messages_template_id FOREIGN KEY (template_id) REFERENCES public.sms_templates(id);


--
-- Name: sms_templates fk_sms_templates_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_templates
    ADD CONSTRAINT fk_sms_templates_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: sms_templates fk_sms_templates_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_templates
    ADD CONSTRAINT fk_sms_templates_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: sms_templates fk_sms_templates_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_templates
    ADD CONSTRAINT fk_sms_templates_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: sms_templates fk_sms_templates_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_templates
    ADD CONSTRAINT fk_sms_templates_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: stored_objects fk_stored_objects_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stored_objects
    ADD CONSTRAINT fk_stored_objects_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: support_tickets fk_support_tickets_reporter_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_tickets
    ADD CONSTRAINT fk_support_tickets_reporter_user_id_users FOREIGN KEY (reporter_user_id) REFERENCES public.users(id);


--
-- Name: support_tickets fk_support_tickets_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_tickets
    ADD CONSTRAINT fk_support_tickets_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: time_clock_entries fk_time_clock_entries_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_entries
    ADD CONSTRAINT fk_time_clock_entries_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: time_clock_entries fk_time_clock_entries_deleted_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_entries
    ADD CONSTRAINT fk_time_clock_entries_deleted_by_users FOREIGN KEY (deleted_by) REFERENCES public.users(id);


--
-- Name: time_clock_entries fk_time_clock_entries_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_entries
    ADD CONSTRAINT fk_time_clock_entries_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: time_clock_entry_edits fk_time_clock_entry_edits_edited_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_entry_edits
    ADD CONSTRAINT fk_time_clock_entry_edits_edited_by_users FOREIGN KEY (edited_by) REFERENCES public.users(id);


--
-- Name: time_clock_entry_edits fk_time_clock_entry_edits_entry_id_time_clock_entries; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_entry_edits
    ADD CONSTRAINT fk_time_clock_entry_edits_entry_id_time_clock_entries FOREIGN KEY (entry_id) REFERENCES public.time_clock_entries(id);


--
-- Name: time_clock_entry_edits fk_time_clock_entry_edits_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_entry_edits
    ADD CONSTRAINT fk_time_clock_entry_edits_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: time_clock_periods fk_time_clock_periods_approved_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_periods
    ADD CONSTRAINT fk_time_clock_periods_approved_by_users FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: time_clock_periods fk_time_clock_periods_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_periods
    ADD CONSTRAINT fk_time_clock_periods_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: time_clock_periods fk_time_clock_periods_locked_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_periods
    ADD CONSTRAINT fk_time_clock_periods_locked_by_users FOREIGN KEY (locked_by) REFERENCES public.users(id);


--
-- Name: time_clock_periods fk_time_clock_periods_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_periods
    ADD CONSTRAINT fk_time_clock_periods_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: time_clock_periods fk_time_clock_periods_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_periods
    ADD CONSTRAINT fk_time_clock_periods_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: time_clock_periods fk_time_clock_periods_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_periods
    ADD CONSTRAINT fk_time_clock_periods_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: time_clock_settings fk_time_clock_settings_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_settings
    ADD CONSTRAINT fk_time_clock_settings_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: time_clock_settings fk_time_clock_settings_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_settings
    ADD CONSTRAINT fk_time_clock_settings_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: treatment_plan_item_icd_codes fk_treatment_plan_item_icd_codes_icd_code_id_icd_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_item_icd_codes
    ADD CONSTRAINT fk_treatment_plan_item_icd_codes_icd_code_id_icd_codes FOREIGN KEY (icd_code_id) REFERENCES public.icd_codes(id);


--
-- Name: treatment_plan_item_icd_codes fk_treatment_plan_item_icd_codes_plan_item_id_treatment_98c7; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_item_icd_codes
    ADD CONSTRAINT fk_treatment_plan_item_icd_codes_plan_item_id_treatment_98c7 FOREIGN KEY (plan_item_id) REFERENCES public.treatment_plan_items(id) ON DELETE CASCADE;


--
-- Name: treatment_plan_items fk_treatment_plan_items_counselor_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_items
    ADD CONSTRAINT fk_treatment_plan_items_counselor_user_id_users FOREIGN KEY (counselor_user_id) REFERENCES public.users(id);


--
-- Name: treatment_plan_items fk_treatment_plan_items_coverage_rule; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_items
    ADD CONSTRAINT fk_treatment_plan_items_coverage_rule FOREIGN KEY (coverage_rule_id) REFERENCES public.insurance_coverage_rules(id);


--
-- Name: treatment_plan_items fk_treatment_plan_items_created_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_items
    ADD CONSTRAINT fk_treatment_plan_items_created_by_users FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: treatment_plan_items fk_treatment_plan_items_fee_schedule_id_fee_schedules; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_items
    ADD CONSTRAINT fk_treatment_plan_items_fee_schedule_id_fee_schedules FOREIGN KEY (fee_schedule_id) REFERENCES public.fee_schedules(id);


--
-- Name: treatment_plan_items fk_treatment_plan_items_material_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_items
    ADD CONSTRAINT fk_treatment_plan_items_material_id FOREIGN KEY (material_id) REFERENCES public.chart_materials(id);


--
-- Name: treatment_plan_items fk_treatment_plan_items_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_items
    ADD CONSTRAINT fk_treatment_plan_items_provider_id_providers FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: treatment_plan_items fk_treatment_plan_items_referral_id_referrals; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_items
    ADD CONSTRAINT fk_treatment_plan_items_referral_id_referrals FOREIGN KEY (referral_id) REFERENCES public.referrals(id);


--
-- Name: treatment_plan_items fk_treatment_plan_items_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_items
    ADD CONSTRAINT fk_treatment_plan_items_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: user_presence fk_up_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_presence
    ADD CONSTRAINT fk_up_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: user_presence fk_up_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_presence
    ADD CONSTRAINT fk_up_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_group_memberships fk_user_group_memberships_group_id_user_groups; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_memberships
    ADD CONSTRAINT fk_user_group_memberships_group_id_user_groups FOREIGN KEY (group_id) REFERENCES public.user_groups(id);


--
-- Name: user_group_memberships fk_user_group_memberships_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_memberships
    ADD CONSTRAINT fk_user_group_memberships_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: user_group_memberships fk_user_group_memberships_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_memberships
    ADD CONSTRAINT fk_user_group_memberships_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_group_rights fk_user_group_rights_group_id_user_groups; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_rights
    ADD CONSTRAINT fk_user_group_rights_group_id_user_groups FOREIGN KEY (group_id) REFERENCES public.user_groups(id);


--
-- Name: user_group_rights fk_user_group_rights_permission_id_permissions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_rights
    ADD CONSTRAINT fk_user_group_rights_permission_id_permissions FOREIGN KEY (permission_id) REFERENCES public.permissions(id);


--
-- Name: user_group_rights fk_user_group_rights_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_rights
    ADD CONSTRAINT fk_user_group_rights_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: user_groups fk_user_groups_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_groups
    ADD CONSTRAINT fk_user_groups_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: user_ip_rules fk_user_ip_rules_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_ip_rules
    ADD CONSTRAINT fk_user_ip_rules_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: user_ip_rules fk_user_ip_rules_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_ip_rules
    ADD CONSTRAINT fk_user_ip_rules_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_login_restrictions fk_user_login_restrictions_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_login_restrictions
    ADD CONSTRAINT fk_user_login_restrictions_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: user_login_restrictions fk_user_login_restrictions_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_login_restrictions
    ADD CONSTRAINT fk_user_login_restrictions_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_preferences fk_user_preferences_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT fk_user_preferences_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: user_preferences fk_user_preferences_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT fk_user_preferences_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_tasks fk_user_tasks_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_tasks
    ADD CONSTRAINT fk_user_tasks_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: user_tasks fk_user_tasks_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_tasks
    ADD CONSTRAINT fk_user_tasks_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_time_clock_config fk_user_time_clock_config_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_time_clock_config
    ADD CONSTRAINT fk_user_time_clock_config_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: user_time_clock_config fk_user_time_clock_config_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_time_clock_config
    ADD CONSTRAINT fk_user_time_clock_config_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: users fk_users_current_office; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_current_office FOREIGN KEY (current_office_id) REFERENCES public.offices(id) ON DELETE SET NULL;


--
-- Name: users fk_users_last_patient_id_patients; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_last_patient_id_patients FOREIGN KEY (last_patient_id) REFERENCES public.patients(id) ON DELETE SET NULL;


--
-- Name: users fk_users_report_access_provider_id_providers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_report_access_provider_id_providers FOREIGN KEY (report_access_provider_id) REFERENCES public.providers(id);


--
-- Name: users fk_users_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: utility_runs fk_utility_runs_office_id_offices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.utility_runs
    ADD CONSTRAINT fk_utility_runs_office_id_offices FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: utility_runs fk_utility_runs_run_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.utility_runs
    ADD CONSTRAINT fk_utility_runs_run_by_users FOREIGN KEY (run_by) REFERENCES public.users(id);


--
-- Name: utility_runs fk_utility_runs_tenant_id_tenants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.utility_runs
    ADD CONSTRAINT fk_utility_runs_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: image_details image_details_image_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_details
    ADD CONSTRAINT image_details_image_group_id_fkey FOREIGN KEY (image_group_id) REFERENCES public.image_groups(id);


--
-- Name: image_details image_details_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_details
    ADD CONSTRAINT image_details_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: image_details image_details_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_details
    ADD CONSTRAINT image_details_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: image_groups image_groups_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_groups
    ADD CONSTRAINT image_groups_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: image_groups image_groups_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_groups
    ADD CONSTRAINT image_groups_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: image_groups image_groups_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_groups
    ADD CONSTRAINT image_groups_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.imaging_templates(id);


--
-- Name: image_groups image_groups_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_groups
    ADD CONSTRAINT image_groups_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: imaging_templates imaging_templates_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.imaging_templates
    ADD CONSTRAINT imaging_templates_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: ins_custom_coverage ins_custom_coverage_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ins_custom_coverage
    ADD CONSTRAINT ins_custom_coverage_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: insurance_carriers insurance_carriers_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_carriers
    ADD CONSTRAINT insurance_carriers_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: insurance_claims insurance_claims_billing_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_claims
    ADD CONSTRAINT insurance_claims_billing_provider_id_fkey FOREIGN KEY (billing_provider_id) REFERENCES public.providers(id);


--
-- Name: insurance_claims insurance_claims_carrier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_claims
    ADD CONSTRAINT insurance_claims_carrier_id_fkey FOREIGN KEY (carrier_id) REFERENCES public.insurance_carriers(id);


--
-- Name: insurance_claims insurance_claims_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_claims
    ADD CONSTRAINT insurance_claims_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: insurance_claims insurance_claims_ins_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_claims
    ADD CONSTRAINT insurance_claims_ins_plan_id_fkey FOREIGN KEY (ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: insurance_claims insurance_claims_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_claims
    ADD CONSTRAINT insurance_claims_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: insurance_claims insurance_claims_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_claims
    ADD CONSTRAINT insurance_claims_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: insurance_claims insurance_claims_treating_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_claims
    ADD CONSTRAINT insurance_claims_treating_provider_id_fkey FOREIGN KEY (treating_provider_id) REFERENCES public.providers(id);


--
-- Name: insurance_coverage_rules insurance_coverage_rules_ins_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_coverage_rules
    ADD CONSTRAINT insurance_coverage_rules_ins_plan_id_fkey FOREIGN KEY (ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: insurance_plans insurance_plans_carrier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plans
    ADD CONSTRAINT insurance_plans_carrier_id_fkey FOREIGN KEY (carrier_id) REFERENCES public.insurance_carriers(id);


--
-- Name: insurance_plans insurance_plans_employer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plans
    ADD CONSTRAINT insurance_plans_employer_id_fkey FOREIGN KEY (employer_id) REFERENCES public.employers(id);


--
-- Name: insurance_plans insurance_plans_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_plans
    ADD CONSTRAINT insurance_plans_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: insurance_subscribers insurance_subscribers_ins_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_subscribers
    ADD CONSTRAINT insurance_subscribers_ins_plan_id_fkey FOREIGN KEY (ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: insurance_subscribers insurance_subscribers_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_subscribers
    ADD CONSTRAINT insurance_subscribers_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: insurance_subscribers insurance_subscribers_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insurance_subscribers
    ADD CONSTRAINT insurance_subscribers_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: ledger_insurance_details ledger_insurance_details_claim_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ledger_insurance_details
    ADD CONSTRAINT ledger_insurance_details_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES public.insurance_claims(id);


--
-- Name: ledger_insurance_details ledger_insurance_details_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ledger_insurance_details
    ADD CONSTRAINT ledger_insurance_details_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: ledger_insurance_details ledger_insurance_details_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ledger_insurance_details
    ADD CONSTRAINT ledger_insurance_details_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: ledger_insurance_details ledger_insurance_details_prim_ins_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ledger_insurance_details
    ADD CONSTRAINT ledger_insurance_details_prim_ins_plan_id_fkey FOREIGN KEY (prim_ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: ledger_insurance_details ledger_insurance_details_procedure_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ledger_insurance_details
    ADD CONSTRAINT ledger_insurance_details_procedure_id_fkey FOREIGN KEY (procedure_id) REFERENCES public.patient_procedures(id);


--
-- Name: ledger_insurance_details ledger_insurance_details_sec_ins_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ledger_insurance_details
    ADD CONSTRAINT ledger_insurance_details_sec_ins_plan_id_fkey FOREIGN KEY (sec_ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: ledger_insurance_details ledger_insurance_details_ter_ins_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ledger_insurance_details
    ADD CONSTRAINT ledger_insurance_details_ter_ins_plan_id_fkey FOREIGN KEY (ter_ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: letter_templates letter_templates_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.letter_templates
    ADD CONSTRAINT letter_templates_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: medical_history_details medical_history_details_history_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_history_details
    ADD CONSTRAINT medical_history_details_history_id_fkey FOREIGN KEY (history_id) REFERENCES public.medical_history_records(id);


--
-- Name: medical_history_records medical_history_records_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_history_records
    ADD CONSTRAINT medical_history_records_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: medical_history_records medical_history_records_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_history_records
    ADD CONSTRAINT medical_history_records_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: medical_history_records medical_history_records_signature_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_history_records
    ADD CONSTRAINT medical_history_records_signature_id_fkey FOREIGN KEY (signature_id) REFERENCES public.patient_signatures(id);


--
-- Name: note_macros note_macros_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_macros
    ADD CONSTRAINT note_macros_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: note_macros note_macros_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_macros
    ADD CONSTRAINT note_macros_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: office_groups office_groups_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.office_groups
    ADD CONSTRAINT office_groups_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: offices offices_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offices
    ADD CONSTRAINT offices_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: offices offices_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offices
    ADD CONSTRAINT offices_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: operatories operatories_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.operatories
    ADD CONSTRAINT operatories_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: ortho_plans ortho_plans_ins_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ortho_plans
    ADD CONSTRAINT ortho_plans_ins_plan_id_fkey FOREIGN KEY (ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: ortho_plans ortho_plans_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ortho_plans
    ADD CONSTRAINT ortho_plans_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: ortho_plans ortho_plans_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ortho_plans
    ADD CONSTRAINT ortho_plans_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: ortho_plans ortho_plans_procedure_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ortho_plans
    ADD CONSTRAINT ortho_plans_procedure_code_fkey FOREIGN KEY (procedure_code) REFERENCES public.procedure_codes(code);


--
-- Name: ortho_plans ortho_plans_sec_ins_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ortho_plans
    ADD CONSTRAINT ortho_plans_sec_ins_plan_id_fkey FOREIGN KEY (sec_ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: ortho_plans ortho_plans_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ortho_plans
    ADD CONSTRAINT ortho_plans_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_alerts patient_alerts_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_alerts
    ADD CONSTRAINT patient_alerts_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_alerts patient_alerts_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_alerts
    ADD CONSTRAINT patient_alerts_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_ins_payment_plans patient_ins_payment_plans_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_ins_payment_plans
    ADD CONSTRAINT patient_ins_payment_plans_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_ins_payment_plans patient_ins_payment_plans_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_ins_payment_plans
    ADD CONSTRAINT patient_ins_payment_plans_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_insurance patient_insurance_ins_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_insurance
    ADD CONSTRAINT patient_insurance_ins_plan_id_fkey FOREIGN KEY (ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: patient_insurance patient_insurance_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_insurance
    ADD CONSTRAINT patient_insurance_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_insurance patient_insurance_subscriber_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_insurance
    ADD CONSTRAINT patient_insurance_subscriber_id_fkey FOREIGN KEY (subscriber_id) REFERENCES public.insurance_subscribers(id);


--
-- Name: patient_notes patient_notes_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_notes
    ADD CONSTRAINT patient_notes_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_notes patient_notes_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_notes
    ADD CONSTRAINT patient_notes_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: patient_notes patient_notes_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_notes
    ADD CONSTRAINT patient_notes_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_payment_plans patient_payment_plans_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payment_plans
    ADD CONSTRAINT patient_payment_plans_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: patient_payment_plans patient_payment_plans_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payment_plans
    ADD CONSTRAINT patient_payment_plans_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_payment_plans patient_payment_plans_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payment_plans
    ADD CONSTRAINT patient_payment_plans_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_payments patient_payments_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payments
    ADD CONSTRAINT patient_payments_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_payments patient_payments_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payments
    ADD CONSTRAINT patient_payments_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: patient_payments patient_payments_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payments
    ADD CONSTRAINT patient_payments_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_payments patient_payments_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_payments
    ADD CONSTRAINT patient_payments_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: patient_procedures patient_procedures_appointment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT patient_procedures_appointment_id_fkey FOREIGN KEY (appointment_id) REFERENCES public.appointments(id);


--
-- Name: patient_procedures patient_procedures_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT patient_procedures_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_procedures patient_procedures_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT patient_procedures_material_id_fkey FOREIGN KEY (material_id) REFERENCES public.chart_materials(id);


--
-- Name: patient_procedures patient_procedures_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT patient_procedures_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: patient_procedures patient_procedures_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT patient_procedures_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_procedures patient_procedures_procedure_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT patient_procedures_procedure_code_fkey FOREIGN KEY (procedure_code) REFERENCES public.procedure_codes(code);


--
-- Name: patient_procedures patient_procedures_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT patient_procedures_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: patient_recalls patient_recalls_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_recalls
    ADD CONSTRAINT patient_recalls_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_recalls patient_recalls_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_recalls
    ADD CONSTRAINT patient_recalls_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: patient_recalls patient_recalls_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_recalls
    ADD CONSTRAINT patient_recalls_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_recalls patient_recalls_procedure_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_recalls
    ADD CONSTRAINT patient_recalls_procedure_code_fkey FOREIGN KEY (procedure_code) REFERENCES public.procedure_codes(code);


--
-- Name: patient_reg_plans patient_reg_plans_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_reg_plans
    ADD CONSTRAINT patient_reg_plans_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: patient_reg_plans patient_reg_plans_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_reg_plans
    ADD CONSTRAINT patient_reg_plans_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_reg_plans patient_reg_plans_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_reg_plans
    ADD CONSTRAINT patient_reg_plans_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_sec_ins_payment_plans patient_sec_ins_payment_plans_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_sec_ins_payment_plans
    ADD CONSTRAINT patient_sec_ins_payment_plans_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_sec_ins_payment_plans patient_sec_ins_payment_plans_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_sec_ins_payment_plans
    ADD CONSTRAINT patient_sec_ins_payment_plans_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: patient_signatures patient_signatures_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_signatures
    ADD CONSTRAINT patient_signatures_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patient_signatures patient_signatures_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_signatures
    ADD CONSTRAINT patient_signatures_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patients patients_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT patients_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: patients patients_home_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT patients_home_office_id_fkey FOREIGN KEY (home_office_id) REFERENCES public.offices(id);


--
-- Name: patients patients_preferred_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT patients_preferred_provider_id_fkey FOREIGN KEY (preferred_provider_id) REFERENCES public.providers(id);


--
-- Name: patients patients_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT patients_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: payment_allocations payment_allocations_claim_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_allocations
    ADD CONSTRAINT payment_allocations_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES public.insurance_claims(id);


--
-- Name: payment_allocations payment_allocations_ins_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_allocations
    ADD CONSTRAINT payment_allocations_ins_plan_id_fkey FOREIGN KEY (ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: payment_allocations payment_allocations_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_allocations
    ADD CONSTRAINT payment_allocations_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: payment_allocations payment_allocations_payment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_allocations
    ADD CONSTRAINT payment_allocations_payment_id_fkey FOREIGN KEY (payment_id) REFERENCES public.patient_payments(id);


--
-- Name: payment_allocations payment_allocations_procedure_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_allocations
    ADD CONSTRAINT payment_allocations_procedure_id_fkey FOREIGN KEY (procedure_id) REFERENCES public.patient_procedures(id);


--
-- Name: payment_allocations payment_allocations_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_allocations
    ADD CONSTRAINT payment_allocations_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: perio_chart_activity perio_chart_activity_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_chart_activity
    ADD CONSTRAINT perio_chart_activity_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: perio_chart_activity perio_chart_activity_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_chart_activity
    ADD CONSTRAINT perio_chart_activity_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: perio_chart_settings perio_chart_settings_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_chart_settings
    ADD CONSTRAINT perio_chart_settings_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: perio_exam_details perio_exam_details_exam_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_exam_details
    ADD CONSTRAINT perio_exam_details_exam_id_fkey FOREIGN KEY (exam_id) REFERENCES public.perio_exams(id);


--
-- Name: perio_exams perio_exams_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_exams
    ADD CONSTRAINT perio_exams_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: perio_exams perio_exams_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_exams
    ADD CONSTRAINT perio_exams_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: perio_exams perio_exams_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.perio_exams
    ADD CONSTRAINT perio_exams_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: postcard_templates postcard_templates_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.postcard_templates
    ADD CONSTRAINT postcard_templates_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: postcard_templates postcard_templates_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.postcard_templates
    ADD CONSTRAINT postcard_templates_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: prescription_library prescription_library_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescription_library
    ADD CONSTRAINT prescription_library_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: prescriptions prescriptions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescriptions
    ADD CONSTRAINT prescriptions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: prescriptions prescriptions_library_rx_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescriptions
    ADD CONSTRAINT prescriptions_library_rx_id_fkey FOREIGN KEY (library_rx_id) REFERENCES public.prescription_library(id);


--
-- Name: prescriptions prescriptions_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescriptions
    ADD CONSTRAINT prescriptions_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: prescriptions prescriptions_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescriptions
    ADD CONSTRAINT prescriptions_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: prescriptions prescriptions_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prescriptions
    ADD CONSTRAINT prescriptions_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: progress_notes progress_notes_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.progress_notes
    ADD CONSTRAINT progress_notes_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: progress_notes progress_notes_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.progress_notes
    ADD CONSTRAINT progress_notes_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: progress_notes progress_notes_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.progress_notes
    ADD CONSTRAINT progress_notes_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: provider_insurance_ids provider_insurance_ids_carrier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_insurance_ids
    ADD CONSTRAINT provider_insurance_ids_carrier_id_fkey FOREIGN KEY (carrier_id) REFERENCES public.insurance_carriers(id);


--
-- Name: provider_insurance_ids provider_insurance_ids_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_insurance_ids
    ADD CONSTRAINT provider_insurance_ids_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: provider_insurance_ids provider_insurance_ids_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_insurance_ids
    ADD CONSTRAINT provider_insurance_ids_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: provider_route_slips provider_route_slips_procedure_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_route_slips
    ADD CONSTRAINT provider_route_slips_procedure_code_fkey FOREIGN KEY (procedure_code) REFERENCES public.procedure_codes(code);


--
-- Name: provider_route_slips provider_route_slips_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_route_slips
    ADD CONSTRAINT provider_route_slips_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: provider_route_slips provider_route_slips_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_route_slips
    ADD CONSTRAINT provider_route_slips_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: providers providers_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT providers_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: providers providers_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT providers_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: questionnaire_headers questionnaire_headers_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.questionnaire_headers
    ADD CONSTRAINT questionnaire_headers_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: questionnaire_options questionnaire_options_questionnaire_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.questionnaire_options
    ADD CONSTRAINT questionnaire_options_questionnaire_id_fkey FOREIGN KEY (questionnaire_id) REFERENCES public.questionnaire_headers(id) ON DELETE CASCADE;


--
-- Name: referral_demog_details referral_demog_details_demog_header_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_demog_details
    ADD CONSTRAINT referral_demog_details_demog_header_id_fkey FOREIGN KEY (demog_header_id) REFERENCES public.referral_demog_headers(id);


--
-- Name: referral_demog_details referral_demog_details_referral_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_demog_details
    ADD CONSTRAINT referral_demog_details_referral_id_fkey FOREIGN KEY (referral_id) REFERENCES public.referrals(id);


--
-- Name: referral_demog_details referral_demog_details_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_demog_details
    ADD CONSTRAINT referral_demog_details_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: referral_demog_headers referral_demog_headers_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_demog_headers
    ADD CONSTRAINT referral_demog_headers_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: referrals referrals_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referrals
    ADD CONSTRAINT referrals_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: referrals referrals_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referrals
    ADD CONSTRAINT referrals_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: referrals referrals_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referrals
    ADD CONSTRAINT referrals_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: referrals referrals_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referrals
    ADD CONSTRAINT referrals_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: refresh_tokens refresh_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: sms_messages sms_messages_appointment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_messages
    ADD CONSTRAINT sms_messages_appointment_id_fkey FOREIGN KEY (appointment_id) REFERENCES public.appointments(id);


--
-- Name: sms_messages sms_messages_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_messages
    ADD CONSTRAINT sms_messages_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: sms_messages sms_messages_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_messages
    ADD CONSTRAINT sms_messages_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: sms_messages sms_messages_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_messages
    ADD CONSTRAINT sms_messages_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: sms_messages sms_messages_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sms_messages
    ADD CONSTRAINT sms_messages_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: time_clock_entries time_clock_entries_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_entries
    ADD CONSTRAINT time_clock_entries_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: time_clock_entries time_clock_entries_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_entries
    ADD CONSTRAINT time_clock_entries_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: time_clock_entries time_clock_entries_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.time_clock_entries
    ADD CONSTRAINT time_clock_entries_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: treatment_plan_insurance_details treatment_plan_insurance_details_ins_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_insurance_details
    ADD CONSTRAINT treatment_plan_insurance_details_ins_plan_id_fkey FOREIGN KEY (ins_plan_id) REFERENCES public.insurance_plans(id);


--
-- Name: treatment_plan_insurance_details treatment_plan_insurance_details_plan_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_insurance_details
    ADD CONSTRAINT treatment_plan_insurance_details_plan_item_id_fkey FOREIGN KEY (plan_item_id) REFERENCES public.treatment_plan_items(id);


--
-- Name: treatment_plan_items treatment_plan_items_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_items
    ADD CONSTRAINT treatment_plan_items_plan_id_fkey FOREIGN KEY (plan_id) REFERENCES public.treatment_plans(id);


--
-- Name: treatment_plan_items treatment_plan_items_procedure_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plan_items
    ADD CONSTRAINT treatment_plan_items_procedure_code_fkey FOREIGN KEY (procedure_code) REFERENCES public.procedure_codes(code);


--
-- Name: treatment_plans treatment_plans_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plans
    ADD CONSTRAINT treatment_plans_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: treatment_plans treatment_plans_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plans
    ADD CONSTRAINT treatment_plans_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: treatment_plans treatment_plans_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatment_plans
    ADD CONSTRAINT treatment_plans_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: user_offices user_offices_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_offices
    ADD CONSTRAINT user_offices_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id);


--
-- Name: user_offices user_offices_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_offices
    ADD CONSTRAINT user_offices_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: users users_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: users users_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- PostgreSQL database dump complete
--

\unrestrict xv8v52yaMyBvp4FxRamNxYKB9bEITvRvC5EpBjrvASJG8jXSUTUu2mgfIyyAdbC

