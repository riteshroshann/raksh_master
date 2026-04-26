CREATE TABLE IF NOT EXISTS consent_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL,
    purpose VARCHAR(50) NOT NULL CHECK (purpose IN (
        'data_storage', 'data_processing', 'sharing_with_doctor',
        'abdm_linking', 'analytics', 'research'
    )),
    granted_at TIMESTAMPTZ,
    withdrawn_at TIMESTAMPTZ,
    withdrawal_method VARCHAR(255),
    consent_text TEXT,
    consent_version INT NOT NULL DEFAULT 1,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT no_duplicate_active_consent UNIQUE (account_id, purpose, withdrawn_at)
);

CREATE INDEX idx_consent_account ON consent_records(account_id);
CREATE INDEX idx_consent_purpose ON consent_records(purpose);
CREATE INDEX idx_consent_active ON consent_records(account_id, purpose) WHERE withdrawn_at IS NULL;

CREATE OR REPLACE FUNCTION execute_right_to_erasure(p_account_id UUID)
RETURNS VOID AS $$
DECLARE
    v_member_ids UUID[];
    v_member_id UUID;
BEGIN
    SELECT ARRAY_AGG(id) INTO v_member_ids
    FROM family_members
    WHERE account_id = p_account_id;

    IF v_member_ids IS NULL THEN
        RETURN;
    END IF;

    FOREACH v_member_id IN ARRAY v_member_ids LOOP
        UPDATE report_parameters
        SET value_numeric = NULL,
            value_text = '[REDACTED]',
            lab_range_low = NULL,
            lab_range_high = NULL,
            indian_range_low = NULL,
            indian_range_high = NULL,
            specimen_type = NULL,
            methodology = NULL
        WHERE member_id = v_member_id;

        UPDATE documents
        SET lab_name = '[REDACTED]',
            doctor_name = '[REDACTED]',
            notes = NULL,
            tags = NULL
        WHERE member_id = v_member_id;
    END LOOP;

    UPDATE family_members
    SET name = '[REDACTED]',
        abha_id = NULL,
        blood_group = NULL,
        emergency_contact_name = NULL,
        emergency_contact_phone = NULL,
        allergies = NULL,
        chronic_conditions = NULL,
        updated_at = NOW()
    WHERE account_id = p_account_id;

    UPDATE consent_records
    SET withdrawn_at = NOW(),
        withdrawal_method = 'RIGHT_TO_ERASURE'
    WHERE account_id = p_account_id
    AND withdrawn_at IS NULL;

    INSERT INTO audit_log (event, account_id, details)
    VALUES (
        'RIGHT_TO_ERASURE_COMPLETED',
        p_account_id,
        jsonb_build_object(
            'members_affected', array_length(v_member_ids, 1),
            'executed_at', NOW()::text
        )
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
