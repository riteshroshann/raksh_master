CREATE TABLE audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event       TEXT NOT NULL,
    account_id  UUID,
    details     JSONB,
    executed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_account ON audit_log(account_id);
CREATE INDEX idx_audit_event ON audit_log(event);
CREATE INDEX idx_audit_time ON audit_log(executed_at);

REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;
REVOKE UPDATE, DELETE ON audit_log FROM authenticated;
REVOKE UPDATE, DELETE ON audit_log FROM anon;
