-- Blocklist Management Platform — initial schema
-- Idempotent: safe to run on every startup

CREATE TABLE IF NOT EXISTS blocklist_entries (
    id          SERIAL PRIMARY KEY,
    list_name   TEXT        NOT NULL,
    ip          INET        NOT NULL,
    reason      TEXT        NOT NULL,
    added_by    TEXT        NOT NULL,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_list_ip UNIQUE (list_name, ip)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id          SERIAL PRIMARY KEY,
    list_name   TEXT        NOT NULL,
    ip          INET        NOT NULL,
    action      TEXT        NOT NULL CHECK (action IN ('add', 'remove', 'expire')),
    user_email  TEXT        NOT NULL,
    reason      TEXT,
    expires_at  TIMESTAMPTZ,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entries_list_name ON blocklist_entries (list_name);
CREATE INDEX IF NOT EXISTS idx_entries_expires_at ON blocklist_entries (expires_at);
CREATE INDEX IF NOT EXISTS idx_audit_ip            ON audit_logs (ip);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp     ON audit_logs (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_list_name     ON audit_logs (list_name);
