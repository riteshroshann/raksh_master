CREATE TABLE consent_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id          UUID NOT NULL REFERENCES auth.users(id),
    purpose             TEXT NOT NULL,
    granted_at          TIMESTAMPTZ,
    withdrawn_at        TIMESTAMPTZ,
    withdrawal_method   TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE consent_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own consent" ON consent_records
    FOR ALL USING (account_id = auth.uid());

CREATE OR REPLACE FUNCTION execute_right_to_erasure(p_account_id UUID)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    UPDATE family_members
        SET name = 'REDACTED', dob = '1900-01-01'
        WHERE account_id = p_account_id;

    UPDATE documents
        SET doctor_name = NULL, lab_name = NULL
        WHERE member_id IN (
            SELECT id FROM family_members WHERE account_id = p_account_id
        );

    INSERT INTO audit_log(event, account_id, executed_at)
        VALUES ('RIGHT_TO_ERASURE', p_account_id, NOW());
END;
$$;
