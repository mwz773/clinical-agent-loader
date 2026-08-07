CREATE TABLE IF NOT EXISTS ingestion_files (
    source_s3_key TEXT PRIMARY KEY,
    source_etag TEXT,
    status TEXT NOT NULL CHECK (status IN ('loaded', 'skipped', 'failed')),
    patient_id TEXT,
    resource_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    full_name JSONB NOT NULL DEFAULT '[]'::jsonb,
    birth_date DATE,
    gender TEXT,
    race TEXT,
    ethnicity TEXT,
    source_s3_key TEXT NOT NULL,
    raw_resource JSONB NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS encounters (
    encounter_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    start_at TIMESTAMPTZ,
    end_at TIMESTAMPTZ,
    encounter_class TEXT,
    encounter_type TEXT,
    source_s3_key TEXT NOT NULL,
    raw_resource JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS encounters_patient_id_idx
    ON encounters (patient_id);

CREATE TABLE IF NOT EXISTS conditions (
    condition_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    encounter_id TEXT REFERENCES encounters(encounter_id) ON DELETE SET NULL,
    code_system TEXT,
    code TEXT,
    description TEXT,
    clinical_status TEXT,
    onset_at TIMESTAMPTZ,
    abatement_at TIMESTAMPTZ,
    source_s3_key TEXT NOT NULL,
    raw_resource JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS conditions_patient_id_idx
    ON conditions (patient_id);

CREATE INDEX IF NOT EXISTS conditions_code_idx
    ON conditions (code);

CREATE TABLE IF NOT EXISTS medications (
    medication_request_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    encounter_id TEXT REFERENCES encounters(encounter_id) ON DELETE SET NULL,
    code_system TEXT,
    code TEXT,
    description TEXT,
    status TEXT,
    intent TEXT,
    authored_at TIMESTAMPTZ,
    source_s3_key TEXT NOT NULL,
    raw_resource JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS medications_patient_id_idx
    ON medications (patient_id);

CREATE INDEX IF NOT EXISTS medications_code_idx
    ON medications (code);

CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    encounter_id TEXT REFERENCES encounters(encounter_id) ON DELETE SET NULL,
    code_system TEXT,
    code TEXT,
    description TEXT,
    status TEXT,
    observed_at TIMESTAMPTZ,
    value_json JSONB,
    source_s3_key TEXT NOT NULL,
    raw_resource JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS observations_patient_id_idx
    ON observations (patient_id);

CREATE INDEX IF NOT EXISTS observations_code_idx
    ON observations (code);

CREATE TABLE IF NOT EXISTS clinical_notes (
    note_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    encounter_id TEXT REFERENCES encounters(encounter_id) ON DELETE SET NULL,
    note_date TIMESTAMPTZ,
    note_text TEXT NOT NULL,
    source_s3_key TEXT NOT NULL,
    raw_resource JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS clinical_notes_patient_id_idx
    ON clinical_notes (patient_id);

CREATE INDEX IF NOT EXISTS clinical_notes_encounter_id_idx
    ON clinical_notes (encounter_id);