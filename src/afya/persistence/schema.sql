-- Afya Yangu / Mlinzi server schema (spec §15.2 PostgreSQL 16+)
-- Idempotent; deployed by examples/deploy_schema.py or afya.persistence.postgres_store.PostgresStore.deploy()
CREATE SCHEMA IF NOT EXISTS afya;

CREATE TABLE IF NOT EXISTS afya.sync_ops (
	op_id TEXT PRIMARY KEY,
	dataset TEXT NOT NULL CHECK (dataset IN ('symptom_logs', 'temperature', 'case_reports', 'immunisation', 'medication', 'facility', 'content', 'proximity_tokens')),
	server_version INTEGER NOT NULL DEFAULT 0,
	client_ts BIGINT NOT NULL,
	server_ts BIGINT NOT NULL DEFAULT 0,
	payload JSONB NOT NULL DEFAULT '{}'::jsonb,
	attempt INTEGER NOT NULL DEFAULT 0,
	synced BOOLEAN NOT NULL DEFAULT FALSE,
	retry_at_ms BIGINT,
	created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- §16.2's retry schedule, added to a table that may already exist. `CREATE TABLE IF NOT EXISTS`
-- above is a no-op against a deployed database, so without this the column would appear only on
-- fresh installs and the first flush that scheduled a retry would fail on every existing one.
ALTER TABLE afya.sync_ops ADD COLUMN IF NOT EXISTS retry_at_ms BIGINT;

-- Whose queued write each op is. A table of its own rather than a column, because `afya.sync_ops`
-- is the shared contract with both device clients (`proto/local_store/contract.json`) and neither
-- client has a subject to fill — the token travels per request, not per row. The owner is
-- server-side knowledge.
--
-- Written once and never overwritten: a queue rehydrated after a restart has no subject to supply,
-- and an upsert that blanked the owner would lose it at the flush, which is the moment the appeal
-- surface needs it. No foreign key, because the flush deletes and re-inserts the op row.
CREATE TABLE IF NOT EXISTS afya.sync_op_owners (
	op_id TEXT PRIMARY KEY,
	subject_ref TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS afya.consents (
	consent_id TEXT PRIMARY KEY,
	subject_ref TEXT NOT NULL,
	purpose TEXT NOT NULL,
	data_types JSONB NOT NULL DEFAULT '[]'::jsonb,
	retention_days INTEGER NOT NULL CHECK (retention_days BETWEEN 1 AND 3650),
	legal_basis TEXT NOT NULL CHECK (legal_basis IN ('consent', 'legal_obligation', 'legitimate_interest')),
	withdrawn BOOLEAN NOT NULL DEFAULT FALSE,
	created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS afya.facilities (
	facility_id TEXT PRIMARY KEY,
	name TEXT NOT NULL,
	kind TEXT NOT NULL CHECK (kind IN ('treatment_unit', 'ed', 'testing_site', 'pharmacy', 'vaccination_point')),
	county TEXT NOT NULL,
	lat DOUBLE PRECISION NOT NULL CHECK (lat BETWEEN -5 AND 6),
	lon DOUBLE PRECISION NOT NULL CHECK (lon BETWEEN 33 AND 43),
	open_now BOOLEAN NOT NULL DEFAULT TRUE,
	ed_status TEXT,
	crowdload INTEGER NOT NULL DEFAULT 0 CHECK (crowdload BETWEEN 0 AND 100),
	payload JSONB NOT NULL,
	updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sync_ops_pending ON afya.sync_ops (synced) WHERE NOT synced;
CREATE INDEX IF NOT EXISTS idx_consents_subject ON afya.consents (subject_ref, purpose);
CREATE INDEX IF NOT EXISTS idx_facilities_county ON afya.facilities (county);

CREATE TABLE IF NOT EXISTS afya.audit_log (
	entry_id TEXT PRIMARY KEY,
	role TEXT NOT NULL,
	dataset TEXT NOT NULL,
	allowed BOOLEAN NOT NULL,
	ref JSONB NOT NULL DEFAULT '{}'::jsonb,
	at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- §17.4's second sentence, on the table an existing deployment already has. The
-- `CREATE TABLE IF NOT EXISTS` above is a no-op against a database that already carries
-- `audit_log`, so without this the column would appear only on fresh installs and the first
-- insert naming it would fail on every existing one — on the audit path, where a failure is
-- silent and the consequence is that §17.4's record stops being written.
ALTER TABLE afya.audit_log ADD COLUMN IF NOT EXISTS purpose TEXT;