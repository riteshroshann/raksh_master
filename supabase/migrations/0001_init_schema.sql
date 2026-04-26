CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS family_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    dob DATE NOT NULL,
    sex VARCHAR(10) NOT NULL CHECK (sex IN ('male', 'female', 'other')),
    colour_hex VARCHAR(7) NOT NULL DEFAULT '#4A90D9' CHECK (colour_hex ~ '^#[0-9a-fA-F]{6}$'),
    abha_id VARCHAR(14),
    blood_group VARCHAR(5),
    emergency_contact_name VARCHAR(255),
    emergency_contact_phone VARCHAR(20),
    allergies TEXT[],
    chronic_conditions TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_member_per_account UNIQUE (account_id, name, dob)
);

CREATE INDEX idx_family_members_account ON family_members(account_id);
CREATE INDEX idx_family_members_abha ON family_members(abha_id) WHERE abha_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    member_id UUID NOT NULL REFERENCES family_members(id) ON DELETE CASCADE,
    ingest_channel VARCHAR(20) NOT NULL CHECK (ingest_channel IN (
        'upload', 'folder_watch', 'email', 'fax', 'scanner', 'emr_ehr', 'pacs', 'hl7', 'abdm'
    )),
    file_path TEXT NOT NULL,
    doc_type VARCHAR(30) NOT NULL CHECK (doc_type IN (
        'lab_report', 'prescription', 'discharge_summary', 'doctor_notes',
        'pathology_report', 'referral_letter', 'insurance_billing', 'radiology_report',
        'xray', 'mri', 'ct_scan', 'ultrasound', 'ecg_eeg', 'mammogram',
        'vaccination_record', 'surgical_report', 'physiotherapy_notes',
        'dietician_plan', 'mental_health_assessment', 'dental_record',
        'eye_examination', 'consent_form'
    )),
    doc_date DATE,
    lab_name VARCHAR(255),
    doctor_name VARCHAR(255),
    content_hash VARCHAR(64),
    file_size_bytes BIGINT,
    page_count INTEGER,
    processing_status VARCHAR(30) NOT NULL DEFAULT 'received' CHECK (processing_status IN (
        'received', 'preprocessing', 'classifying', 'extracting', 'scoring',
        'validating', 'awaiting_confirmation', 'confirmed', 'failed', 'duplicate'
    )),
    processing_started_at TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    processing_duration_ms FLOAT,
    extraction_model VARCHAR(100),
    classification_confidence FLOAT,
    confirmed_at TIMESTAMPTZ,
    confirmed_by UUID,
    notes TEXT,
    tags TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_member ON documents(member_id);
CREATE INDEX idx_documents_doc_type ON documents(doc_type);
CREATE INDEX idx_documents_hash ON documents(content_hash, member_id);
CREATE INDEX idx_documents_channel ON documents(ingest_channel);
CREATE INDEX idx_documents_status ON documents(processing_status);
CREATE INDEX idx_documents_created ON documents(created_at DESC);
CREATE INDEX idx_documents_doc_date ON documents(doc_date DESC) WHERE doc_date IS NOT NULL;

CREATE TABLE IF NOT EXISTS report_parameters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES family_members(id) ON DELETE CASCADE,
    parameter_name VARCHAR(100) NOT NULL,
    value_numeric FLOAT,
    value_text VARCHAR(500),
    unit VARCHAR(50),
    lab_range_low FLOAT,
    lab_range_high FLOAT,
    indian_range_low FLOAT,
    indian_range_high FLOAT,
    flag VARCHAR(20) DEFAULT 'unconfirmed' CHECK (flag IN (
        'normal', 'above_range', 'below_range', 'critical_high', 'critical_low', 'unconfirmed', 'borderline'
    )),
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    fasting_status VARCHAR(20) DEFAULT 'unknown' CHECK (fasting_status IN ('fasting', 'non_fasting', 'unknown')),
    test_date DATE NOT NULL,
    specimen_type VARCHAR(100),
    methodology VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_report_params_document ON report_parameters(document_id);
CREATE INDEX idx_report_params_member ON report_parameters(member_id);
CREATE INDEX idx_report_params_name ON report_parameters(parameter_name);
CREATE INDEX idx_report_params_test_date ON report_parameters(test_date DESC);
CREATE INDEX idx_report_params_member_param ON report_parameters(member_id, parameter_name, test_date DESC);
CREATE INDEX idx_report_params_flag ON report_parameters(flag) WHERE flag NOT IN ('normal', 'unconfirmed');
