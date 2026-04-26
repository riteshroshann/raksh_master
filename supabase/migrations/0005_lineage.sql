CREATE TABLE extraction_lineage (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parameter_id      UUID NOT NULL REFERENCES report_parameters(id),
    document_id       UUID NOT NULL REFERENCES documents(id),
    extraction_model  TEXT NOT NULL,
    raw_ocr_output    TEXT,
    bounding_box      JSONB,
    confidence_raw    NUMERIC,
    patient_edited    BOOLEAN DEFAULT FALSE,
    original_value    TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_lineage_parameter ON extraction_lineage(parameter_id);
CREATE INDEX idx_lineage_document ON extraction_lineage(document_id);
