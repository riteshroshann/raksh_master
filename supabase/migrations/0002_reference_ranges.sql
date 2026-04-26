CREATE TABLE reference_ranges (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parameter_name   TEXT NOT NULL,
    sex              TEXT CHECK (sex IN ('male','female','any')),
    age_min          INTEGER,
    age_max          INTEGER,
    range_low        NUMERIC,
    range_high       NUMERIC,
    unit             TEXT NOT NULL,
    source           TEXT NOT NULL CHECK (source IN ('ICMR','RSSDI','IHG','lab','western')),
    source_citation  TEXT NOT NULL,
    population       TEXT DEFAULT 'indian',
    version          INTEGER NOT NULL DEFAULT 1,
    approved_by      TEXT,
    approved_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_refrange_lookup
    ON reference_ranges(parameter_name, sex, population);
