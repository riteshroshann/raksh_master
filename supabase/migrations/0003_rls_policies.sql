ALTER TABLE family_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_parameters ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own family" ON family_members
    FOR ALL USING (account_id = auth.uid());

CREATE POLICY "own documents" ON documents
    FOR ALL USING (
        member_id IN (SELECT id FROM family_members WHERE account_id = auth.uid())
    );

CREATE POLICY "own parameters" ON report_parameters
    FOR ALL USING (
        member_id IN (SELECT id FROM family_members WHERE account_id = auth.uid())
    );
