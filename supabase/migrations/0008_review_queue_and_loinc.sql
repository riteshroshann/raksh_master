-- Review Queue for Human-in-the-Loop Verification
-- Low-confidence VLM extractions are routed here for manual review

CREATE TABLE IF NOT EXISTS review_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingest_id TEXT NOT NULL,
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    member_id UUID NOT NULL REFERENCES family_members(id) ON DELETE CASCADE,
    parameter_name TEXT NOT NULL,
    extracted_value TEXT,
    extracted_value_numeric NUMERIC,
    unit TEXT,
    confidence NUMERIC NOT NULL DEFAULT 0.0,
    extraction_model TEXT,
    raw_ocr_output TEXT,
    bounding_box JSONB,
    reason TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('critical', 'high', 'medium', 'low')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_review', 'approved', 'corrected', 'rejected')),
    reviewer_id UUID,
    reviewed_at TIMESTAMPTZ,
    corrected_value TEXT,
    corrected_value_numeric NUMERIC,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_review_queue_priority ON review_queue(priority);
CREATE INDEX IF NOT EXISTS idx_review_queue_member ON review_queue(member_id);
CREATE INDEX IF NOT EXISTS idx_review_queue_created ON review_queue(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_queue_pending_priority ON review_queue(status, priority) WHERE status = 'pending';

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_review_queue_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_review_queue_updated
    BEFORE UPDATE ON review_queue
    FOR EACH ROW
    EXECUTE FUNCTION update_review_queue_timestamp();

-- RLS: Only service role can access review queue
ALTER TABLE review_queue ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on review_queue"
    ON review_queue
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- Review statistics view
CREATE OR REPLACE VIEW review_queue_stats AS
SELECT
    status,
    priority,
    COUNT(*) as count,
    AVG(confidence) as avg_confidence,
    MIN(created_at) as oldest_pending,
    MAX(reviewed_at) as latest_reviewed
FROM review_queue
GROUP BY status, priority
ORDER BY
    CASE priority
        WHEN 'critical' THEN 0
        WHEN 'high' THEN 1
        WHEN 'medium' THEN 2
        WHEN 'low' THEN 3
    END,
    status;

-- LOINC codes lookup table
CREATE TABLE IF NOT EXISTS loinc_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    loinc_code TEXT NOT NULL,
    loinc_name TEXT NOT NULL,
    component TEXT,
    system TEXT,
    unit TEXT,
    parameter_alias TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_loinc_alias ON loinc_codes(parameter_alias);
CREATE INDEX IF NOT EXISTS idx_loinc_code ON loinc_codes(loinc_code);

-- Drug interactions audit log
CREATE TABLE IF NOT EXISTS drug_interaction_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id UUID NOT NULL REFERENCES family_members(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    drug_a TEXT NOT NULL,
    drug_b TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'moderate', 'low')),
    effect TEXT NOT NULL,
    action TEXT NOT NULL,
    acknowledged BOOLEAN NOT NULL DEFAULT false,
    acknowledged_by UUID,
    acknowledged_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_drug_alerts_member ON drug_interaction_alerts(member_id);
CREATE INDEX IF NOT EXISTS idx_drug_alerts_unack ON drug_interaction_alerts(acknowledged) WHERE acknowledged = false;

ALTER TABLE drug_interaction_alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on drug_interaction_alerts"
    ON drug_interaction_alerts
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- Disease protocol findings table
CREATE TABLE IF NOT EXISTS disease_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id UUID NOT NULL REFERENCES family_members(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    disease_category TEXT NOT NULL,
    parameter_name TEXT NOT NULL,
    value NUMERIC,
    status TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'warning', 'attention', 'info')),
    co_monitoring_gaps JSONB,
    trend_alerts JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_disease_findings_member ON disease_findings(member_id);
CREATE INDEX IF NOT EXISTS idx_disease_findings_severity ON disease_findings(severity);
CREATE INDEX IF NOT EXISTS idx_disease_findings_category ON disease_findings(disease_category);

ALTER TABLE disease_findings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on disease_findings"
    ON disease_findings
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
