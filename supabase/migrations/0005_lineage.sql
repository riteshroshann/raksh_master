CREATE TABLE IF NOT EXISTS extraction_lineage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parameter_id UUID NOT NULL REFERENCES report_parameters(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    extraction_model VARCHAR(100) NOT NULL,
    model_version VARCHAR(50),
    raw_ocr_output TEXT,
    bounding_box JSONB,
    confidence_raw FLOAT,
    confidence_threshold FLOAT,
    patient_edited BOOLEAN NOT NULL DEFAULT FALSE,
    original_value TEXT,
    edit_reason VARCHAR(255),
    preprocessing_applied TEXT[],
    extraction_duration_ms FLOAT,
    image_quality VARCHAR(20),
    page_number INT,
    region_of_interest JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_lineage_parameter ON extraction_lineage(parameter_id);
CREATE INDEX idx_lineage_document ON extraction_lineage(document_id);
CREATE INDEX idx_lineage_model ON extraction_lineage(extraction_model);
CREATE INDEX idx_lineage_edited ON extraction_lineage(patient_edited) WHERE patient_edited = TRUE;
CREATE INDEX idx_lineage_created ON extraction_lineage(created_at DESC);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    ingest_id VARCHAR(36) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'started',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_ms FLOAT,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message TEXT,
    error_step VARCHAR(50),
    classification_result VARCHAR(30),
    classification_confidence FLOAT,
    extraction_model VARCHAR(100),
    extraction_field_count INT,
    confidence_above_threshold INT,
    confidence_below_threshold INT,
    patient_edit_count INT DEFAULT 0,
    file_size_bytes BIGINT,
    file_type VARCHAR(50),
    image_quality VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pipeline_runs_document ON pipeline_runs(document_id);
CREATE INDEX idx_pipeline_runs_ingest_id ON pipeline_runs(ingest_id);
CREATE INDEX idx_pipeline_runs_status ON pipeline_runs(status);
CREATE INDEX idx_pipeline_runs_channel ON pipeline_runs(channel);
CREATE INDEX idx_pipeline_runs_created ON pipeline_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS abdm_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id UUID NOT NULL REFERENCES family_members(id) ON DELETE CASCADE,
    abha_id VARCHAR(14) NOT NULL,
    health_id VARCHAR(255),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    verification_method VARCHAR(50),
    consent_artifact_id VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_abdm_link UNIQUE (member_id, abha_id)
);

CREATE INDEX idx_abdm_links_member ON abdm_links(member_id);
CREATE INDEX idx_abdm_links_abha ON abdm_links(abha_id);

CREATE TABLE IF NOT EXISTS notification_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL,
    notify_on_extraction BOOLEAN NOT NULL DEFAULT TRUE,
    notify_on_critical BOOLEAN NOT NULL DEFAULT TRUE,
    notify_on_edit_rate_alert BOOLEAN NOT NULL DEFAULT TRUE,
    notification_email VARCHAR(255),
    notification_phone VARCHAR(20),
    whatsapp_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_notification_pref UNIQUE (account_id)
);

CREATE INDEX idx_notification_account ON notification_preferences(account_id);
