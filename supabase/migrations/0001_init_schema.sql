CREATE TABLE family_members (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    dob         DATE NOT NULL,
    sex         TEXT NOT NULL CHECK (sex IN ('male','female','other')),
    colour_hex  TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id       UUID NOT NULL REFERENCES family_members(id) ON DELETE CASCADE,
    ingest_channel  TEXT NOT NULL CHECK (ingest_channel IN ('upload','email','folder','fax','scanner','emr','pacs')),
    file_path       TEXT NOT NULL,
    doc_type        TEXT NOT NULL CHECK (doc_type IN (
        'lab_report','prescription','discharge_summary','doctor_notes',
        'pathology_report','referral_letter','insurance_billing',
        'xray','mri','ct_scan','ultrasound','ecg_eeg','radiology_report'
    )),
    doc_date        DATE,
    lab_name        TEXT,
    doctor_name     TEXT,
    content_hash    TEXT,
    confirmed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE report_parameters (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id       UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    member_id         UUID NOT NULL REFERENCES family_members(id),
    parameter_name    TEXT NOT NULL,
    value_numeric     NUMERIC,
    value_text        TEXT,
    unit              TEXT,
    lab_range_low     NUMERIC,
    lab_range_high    NUMERIC,
    indian_range_low  NUMERIC,
    indian_range_high NUMERIC,
    flag              TEXT CHECK (flag IN ('normal','above_range','below_range','unconfirmed')),
    confidence        NUMERIC NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    fasting_status    TEXT CHECK (fasting_status IN ('fasting','non_fasting','unknown')),
    test_date         DATE NOT NULL,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_documents_member ON documents(member_id);
CREATE INDEX idx_documents_hash ON documents(content_hash);
CREATE INDEX idx_params_document ON report_parameters(document_id);
CREATE INDEX idx_params_member ON report_parameters(member_id);
CREATE INDEX idx_params_name ON report_parameters(parameter_name);
