ALTER TABLE family_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_parameters ENABLE ROW LEVEL SECURITY;

CREATE POLICY select_own_members ON family_members
    FOR SELECT USING (account_id = auth.uid());

CREATE POLICY insert_own_members ON family_members
    FOR INSERT WITH CHECK (account_id = auth.uid());

CREATE POLICY update_own_members ON family_members
    FOR UPDATE USING (account_id = auth.uid());

CREATE POLICY delete_own_members ON family_members
    FOR DELETE USING (account_id = auth.uid());

CREATE POLICY select_own_documents ON documents
    FOR SELECT USING (
        member_id IN (
            SELECT id FROM family_members WHERE account_id = auth.uid()
        )
    );

CREATE POLICY insert_own_documents ON documents
    FOR INSERT WITH CHECK (
        member_id IN (
            SELECT id FROM family_members WHERE account_id = auth.uid()
        )
    );

CREATE POLICY select_own_parameters ON report_parameters
    FOR SELECT USING (
        member_id IN (
            SELECT id FROM family_members WHERE account_id = auth.uid()
        )
    );

CREATE POLICY insert_own_parameters ON report_parameters
    FOR INSERT WITH CHECK (
        member_id IN (
            SELECT id FROM family_members WHERE account_id = auth.uid()
        )
    );

