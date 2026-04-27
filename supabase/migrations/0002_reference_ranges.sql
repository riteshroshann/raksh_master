CREATE TABLE IF NOT EXISTS reference_ranges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parameter_name VARCHAR(100) NOT NULL,
    sex VARCHAR(10) NOT NULL DEFAULT 'any' CHECK (sex IN ('male', 'female', 'any')),
    age_min INT,
    age_max INT,
    range_low FLOAT,
    range_high FLOAT,
    critical_low FLOAT,
    critical_high FLOAT,
    unit VARCHAR(50) NOT NULL,
    source VARCHAR(50) NOT NULL CHECK (source IN ('icmr', 'rssdi', 'api_india', 'who', 'western', 'ispad', 'fogsi', 'iap')),
    source_citation TEXT NOT NULL,
    population VARCHAR(20) NOT NULL DEFAULT 'indian' CHECK (population IN ('indian', 'western', 'global')),
    version INT NOT NULL DEFAULT 1,
    approved_by VARCHAR(255),
    approved_at TIMESTAMPTZ,
    effective_from DATE NOT NULL DEFAULT CURRENT_DATE,
    effective_to DATE,
    methodology VARCHAR(200),
    specimen_type VARCHAR(100),
    fasting_required BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_range UNIQUE (parameter_name, sex, age_min, age_max, population, version)
);

CREATE INDEX idx_reference_ranges_lookup ON reference_ranges(parameter_name, sex, population);
CREATE INDEX idx_reference_ranges_param ON reference_ranges(parameter_name);
CREATE INDEX idx_reference_ranges_source ON reference_ranges(source);
CREATE INDEX idx_reference_ranges_effective ON reference_ranges(effective_from, effective_to);
