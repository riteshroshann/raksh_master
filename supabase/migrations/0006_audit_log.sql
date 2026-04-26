CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event VARCHAR(100) NOT NULL,
    account_id UUID,
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    request_id VARCHAR(36),
    service_name VARCHAR(50) DEFAULT 'raksh-ingestion',
    environment VARCHAR(20) DEFAULT 'production',
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_event ON audit_log(event);
CREATE INDEX idx_audit_account ON audit_log(account_id) WHERE account_id IS NOT NULL;
CREATE INDEX idx_audit_executed ON audit_log(executed_at DESC);
CREATE INDEX idx_audit_event_time ON audit_log(event, executed_at DESC);

REVOKE UPDATE ON audit_log FROM PUBLIC;
REVOKE DELETE ON audit_log FROM PUBLIC;

CREATE TABLE IF NOT EXISTS metrics_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    total_ingestions INT NOT NULL DEFAULT 0,
    total_confirmations INT NOT NULL DEFAULT 0,
    total_parameters INT NOT NULL DEFAULT 0,
    total_patient_edits INT NOT NULL DEFAULT 0,
    patient_edit_rate FLOAT NOT NULL DEFAULT 0.0,
    average_confidence FLOAT NOT NULL DEFAULT 0.0,
    average_extraction_time_ms FLOAT NOT NULL DEFAULT 0.0,
    extractions_by_doc_type JSONB NOT NULL DEFAULT '{}'::jsonb,
    extractions_by_channel JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence_distribution JSONB NOT NULL DEFAULT '{}'::jsonb,
    top_edited_parameters JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_snapshot_date UNIQUE (snapshot_date)
);

CREATE INDEX idx_metrics_date ON metrics_snapshots(snapshot_date DESC);

CREATE OR REPLACE FUNCTION record_daily_metrics()
RETURNS VOID AS $$
DECLARE
    v_total_ingestions INT;
    v_total_confirmations INT;
    v_total_params INT;
    v_total_edits INT;
    v_edit_rate FLOAT;
    v_avg_confidence FLOAT;
BEGIN
    SELECT COUNT(*) INTO v_total_ingestions FROM documents;
    SELECT COUNT(*) INTO v_total_confirmations FROM documents WHERE confirmed_at IS NOT NULL;
    SELECT COUNT(*) INTO v_total_params FROM extraction_lineage;
    SELECT COUNT(*) INTO v_total_edits FROM extraction_lineage WHERE patient_edited = TRUE;

    v_edit_rate := CASE WHEN v_total_params > 0 THEN (v_total_edits::FLOAT / v_total_params * 100) ELSE 0.0 END;

    SELECT COALESCE(AVG(confidence_raw), 0.0) INTO v_avg_confidence FROM extraction_lineage;

    INSERT INTO metrics_snapshots (
        snapshot_date, total_ingestions, total_confirmations, total_parameters,
        total_patient_edits, patient_edit_rate, average_confidence
    ) VALUES (
        CURRENT_DATE, v_total_ingestions, v_total_confirmations, v_total_params,
        v_total_edits, v_edit_rate, v_avg_confidence
    )
    ON CONFLICT (snapshot_date) DO UPDATE SET
        total_ingestions = EXCLUDED.total_ingestions,
        total_confirmations = EXCLUDED.total_confirmations,
        total_parameters = EXCLUDED.total_parameters,
        total_patient_edits = EXCLUDED.total_patient_edits,
        patient_edit_rate = EXCLUDED.patient_edit_rate,
        average_confidence = EXCLUDED.average_confidence;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_member_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_member_timestamp
    BEFORE UPDATE ON family_members
    FOR EACH ROW
    EXECUTE FUNCTION update_member_timestamp();

CREATE OR REPLACE FUNCTION flag_critical_values()
RETURNS TRIGGER AS $$
DECLARE
    v_ref reference_ranges%ROWTYPE;
BEGIN
    SELECT * INTO v_ref
    FROM reference_ranges
    WHERE parameter_name = NEW.parameter_name
    AND population = 'indian'
    AND (sex = (SELECT sex FROM family_members WHERE id = NEW.member_id) OR sex = 'any')
    ORDER BY version DESC
    LIMIT 1;

    IF v_ref IS NOT NULL AND NEW.value_numeric IS NOT NULL THEN
        IF v_ref.critical_low IS NOT NULL AND NEW.value_numeric < v_ref.critical_low THEN
            NEW.flag = 'critical_low';
        ELSIF v_ref.critical_high IS NOT NULL AND NEW.value_numeric > v_ref.critical_high THEN
            NEW.flag = 'critical_high';
        ELSIF v_ref.range_low IS NOT NULL AND NEW.value_numeric < v_ref.range_low THEN
            NEW.flag = 'below_range';
        ELSIF v_ref.range_high IS NOT NULL AND NEW.value_numeric > v_ref.range_high THEN
            NEW.flag = 'above_range';
        ELSE
            NEW.flag = 'normal';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_flag_critical_values
    BEFORE INSERT ON report_parameters
    FOR EACH ROW
    EXECUTE FUNCTION flag_critical_values();
