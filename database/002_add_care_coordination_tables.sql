CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS clinical_events (
    event_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    encounter_id TEXT REFERENCES encounters(encounter_id) ON DELETE SET NULL,
    resource_type TEXT NOT NULL,
    event_time TIMESTAMPTZ,
    status TEXT,
    code_system TEXT,
    code TEXT,
    description TEXT,
    source_s3_key TEXT NOT NULL,
    raw_resource JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS clinical_events_patient_time_idx
    ON clinical_events (patient_id, event_time DESC);

CREATE INDEX IF NOT EXISTS clinical_events_type_idx
    ON clinical_events (resource_type);

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id UUID PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(patient_id),
    note_id TEXT REFERENCES clinical_notes(note_id) ON DELETE SET NULL,
    model_id TEXT NOT NULL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms INTEGER,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS follow_up_briefs (
    run_id UUID PRIMARY KEY REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    change_summary JSONB NOT NULL,
    review_items JSONB NOT NULL,
    processed_output_s3_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS brief_evidence (
    run_id UUID NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    source_s3_key TEXT NOT NULL,
    PRIMARY KEY (run_id, resource_type, resource_id)
);

INSERT INTO schema_migrations (version)
VALUES ('002_care_coordination')
ON CONFLICT (version) DO NOTHING;