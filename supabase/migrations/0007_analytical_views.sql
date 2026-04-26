CREATE OR REPLACE VIEW v_member_summary AS
SELECT
    fm.id AS member_id,
    fm.account_id,
    fm.name,
    fm.dob,
    fm.sex,
    fm.colour_hex,
    fm.abha_id,
    fm.blood_group,
    fm.chronic_conditions,
    EXTRACT(YEAR FROM AGE(NOW(), fm.dob))::INT AS age,
    COUNT(DISTINCT d.id) AS total_documents,
    COUNT(DISTINCT rp.id) AS total_parameters,
    MAX(d.created_at) AS last_document_at,
    MAX(rp.test_date) AS last_test_date,
    COALESCE(
        ROUND(
            COUNT(CASE WHEN el.patient_edited = TRUE THEN 1 END)::NUMERIC /
            NULLIF(COUNT(el.id), 0) * 100,
            2
        ),
        0
    ) AS patient_edit_rate_pct
FROM family_members fm
LEFT JOIN documents d ON d.member_id = fm.id
LEFT JOIN report_parameters rp ON rp.member_id = fm.id
LEFT JOIN extraction_lineage el ON el.parameter_id = rp.id
GROUP BY fm.id;


CREATE OR REPLACE VIEW v_parameter_latest AS
SELECT DISTINCT ON (rp.member_id, rp.parameter_name)
    rp.id,
    rp.member_id,
    rp.parameter_name,
    rp.value_numeric,
    rp.value_text,
    rp.unit,
    rp.flag,
    rp.confidence,
    rp.test_date,
    rp.indian_range_low,
    rp.indian_range_high,
    rp.lab_range_low,
    rp.lab_range_high,
    rp.fasting_status,
    fm.name AS member_name,
    fm.sex AS member_sex,
    EXTRACT(YEAR FROM AGE(NOW(), fm.dob))::INT AS member_age
FROM report_parameters rp
JOIN family_members fm ON fm.id = rp.member_id
ORDER BY rp.member_id, rp.parameter_name, rp.test_date DESC;


CREATE OR REPLACE VIEW v_critical_alerts AS
SELECT
    rp.id AS parameter_id,
    rp.document_id,
    rp.member_id,
    fm.name AS member_name,
    fm.account_id,
    rp.parameter_name,
    rp.value_numeric,
    rp.unit,
    rp.flag,
    rp.test_date,
    rp.indian_range_low,
    rp.indian_range_high,
    d.doc_type,
    d.lab_name,
    d.doctor_name,
    d.created_at AS ingested_at
FROM report_parameters rp
JOIN family_members fm ON fm.id = rp.member_id
JOIN documents d ON d.id = rp.document_id
WHERE rp.flag IN ('critical_high', 'critical_low', 'above_range', 'below_range')
ORDER BY rp.test_date DESC;


CREATE OR REPLACE VIEW v_extraction_quality AS
SELECT
    el.extraction_model,
    COUNT(el.id) AS total_extractions,
    ROUND(AVG(el.confidence_raw)::NUMERIC, 4) AS avg_confidence,
    ROUND(
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY el.confidence_raw)::NUMERIC,
        4
    ) AS median_confidence,
    ROUND(
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY el.confidence_raw)::NUMERIC,
        4
    ) AS p95_confidence,
    COUNT(CASE WHEN el.patient_edited THEN 1 END) AS total_edits,
    ROUND(
        COUNT(CASE WHEN el.patient_edited THEN 1 END)::NUMERIC /
        NULLIF(COUNT(el.id), 0) * 100,
        2
    ) AS edit_rate_pct,
    ROUND(AVG(el.extraction_duration_ms)::NUMERIC, 2) AS avg_extraction_ms
FROM extraction_lineage el
GROUP BY el.extraction_model
ORDER BY avg_confidence DESC;


CREATE OR REPLACE VIEW v_monthly_ingestion_stats AS
SELECT
    DATE_TRUNC('month', d.created_at)::DATE AS month,
    d.doc_type,
    d.ingest_channel,
    COUNT(d.id) AS document_count,
    COUNT(DISTINCT d.member_id) AS unique_members,
    ROUND(AVG(d.processing_duration_ms)::NUMERIC, 2) AS avg_processing_ms,
    COUNT(CASE WHEN d.processing_status = 'confirmed' THEN 1 END) AS confirmed_count,
    COUNT(CASE WHEN d.processing_status = 'failed' THEN 1 END) AS failed_count
FROM documents d
GROUP BY DATE_TRUNC('month', d.created_at), d.doc_type, d.ingest_channel
ORDER BY month DESC, document_count DESC;


CREATE OR REPLACE VIEW v_parameter_correlations AS
WITH member_latest AS (
    SELECT DISTINCT ON (member_id, parameter_name)
        member_id,
        parameter_name,
        value_numeric,
        test_date
    FROM report_parameters
    WHERE value_numeric IS NOT NULL
    ORDER BY member_id, parameter_name, test_date DESC
)
SELECT
    a.member_id,
    a.parameter_name AS param_a,
    b.parameter_name AS param_b,
    a.value_numeric AS value_a,
    b.value_numeric AS value_b,
    a.test_date AS date_a,
    b.test_date AS date_b
FROM member_latest a
JOIN member_latest b ON a.member_id = b.member_id
    AND a.parameter_name < b.parameter_name
    AND ABS(a.test_date - b.test_date) <= 30;


CREATE OR REPLACE VIEW v_consent_status AS
SELECT
    cr.account_id,
    cr.purpose,
    cr.granted_at,
    cr.withdrawn_at,
    cr.withdrawal_method,
    CASE
        WHEN cr.withdrawn_at IS NOT NULL THEN 'withdrawn'
        WHEN cr.granted_at IS NOT NULL THEN 'active'
        ELSE 'pending'
    END AS status,
    fm.name AS member_name
FROM consent_records cr
LEFT JOIN family_members fm ON fm.account_id = cr.account_id
ORDER BY cr.created_at DESC;


CREATE OR REPLACE VIEW v_duplicate_detection AS
SELECT
    d.content_hash,
    d.member_id,
    fm.name AS member_name,
    COUNT(d.id) AS occurrence_count,
    MIN(d.created_at) AS first_seen,
    MAX(d.created_at) AS last_seen,
    ARRAY_AGG(DISTINCT d.ingest_channel) AS channels
FROM documents d
JOIN family_members fm ON fm.id = d.member_id
WHERE d.content_hash IS NOT NULL
GROUP BY d.content_hash, d.member_id, fm.name
HAVING COUNT(d.id) > 1
ORDER BY occurrence_count DESC;


CREATE OR REPLACE VIEW v_audit_dashboard AS
SELECT
    DATE_TRUNC('hour', al.executed_at)::TIMESTAMPTZ AS hour,
    al.event,
    COUNT(al.id) AS event_count
FROM audit_log al
WHERE al.executed_at > NOW() - INTERVAL '7 days'
GROUP BY DATE_TRUNC('hour', al.executed_at), al.event
ORDER BY hour DESC, event_count DESC;


CREATE OR REPLACE VIEW v_pipeline_performance AS
SELECT
    DATE_TRUNC('day', pr.created_at)::DATE AS day,
    pr.channel,
    COUNT(pr.id) AS total_runs,
    COUNT(CASE WHEN pr.status = 'completed' THEN 1 END) AS completed,
    COUNT(CASE WHEN pr.status = 'failed' THEN 1 END) AS failed,
    ROUND(
        COUNT(CASE WHEN pr.status = 'completed' THEN 1 END)::NUMERIC /
        NULLIF(COUNT(pr.id), 0) * 100,
        2
    ) AS success_rate,
    ROUND(AVG(pr.duration_ms)::NUMERIC, 2) AS avg_duration_ms,
    ROUND(
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY pr.duration_ms)::NUMERIC,
        2
    ) AS p95_duration_ms,
    ROUND(AVG(pr.extraction_field_count)::NUMERIC, 1) AS avg_fields_extracted,
    ROUND(
        AVG(
            CASE WHEN (pr.confidence_above_threshold + pr.confidence_below_threshold) > 0
            THEN pr.confidence_above_threshold::NUMERIC /
                 (pr.confidence_above_threshold + pr.confidence_below_threshold) * 100
            END
        )::NUMERIC,
        2
    ) AS avg_auto_extraction_rate
FROM pipeline_runs pr
GROUP BY DATE_TRUNC('day', pr.created_at), pr.channel
ORDER BY day DESC;


CREATE OR REPLACE VIEW v_reference_range_coverage AS
SELECT
    rr.parameter_name,
    rr.population,
    COUNT(DISTINCT rr.sex) AS sex_variants,
    COUNT(DISTINCT CASE WHEN rr.age_min IS NOT NULL THEN rr.id END) AS age_specific_ranges,
    rr.source,
    rr.source_citation,
    MAX(rr.version) AS latest_version,
    MAX(rr.approved_at) AS last_approved,
    BOOL_OR(rr.fasting_required) AS fasting_required
FROM reference_ranges rr
GROUP BY rr.parameter_name, rr.population, rr.source, rr.source_citation
ORDER BY rr.parameter_name;
