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
	created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
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