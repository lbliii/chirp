CREATE TABLE _chirp_job_schema (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    version smallint NOT NULL CHECK (version > 0)
);

INSERT INTO _chirp_job_schema (singleton, version) VALUES (true, 1);

CREATE TABLE _chirp_job_queues (
    queue_name varchar(128) PRIMARY KEY,
    concurrency_limit smallint NOT NULL CHECK (concurrency_limit BETWEEN 1 AND 1024),
    active_claims smallint NOT NULL DEFAULT 0 CHECK (active_claims BETWEEN 0 AND 1024),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE _chirp_jobs (
    id uuid PRIMARY KEY,
    definition_name varchar(200) NOT NULL,
    payload jsonb NOT NULL,
    payload_version integer NOT NULL CHECK (payload_version BETWEEN 1 AND 2147483647),
    queue_name varchar(128) NOT NULL REFERENCES _chirp_job_queues (queue_name),
    priority smallint NOT NULL CHECK (priority BETWEEN -1000 AND 1000),
    idempotency_key varchar(256),
    max_attempts smallint NOT NULL CHECK (max_attempts BETWEEN 1 AND 100),
    backoff_base_seconds integer NOT NULL CHECK (backoff_base_seconds BETWEEN 0 AND 3600),
    backoff_max_seconds integer NOT NULL CHECK (
        backoff_max_seconds BETWEEN backoff_base_seconds AND 86400
    ),
    state varchar(16) NOT NULL DEFAULT 'pending' CHECK (
        state IN ('pending', 'running', 'succeeded', 'failed')
    ),
    attempts smallint NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 100),
    available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    owner_id varchar(200),
    lease_token uuid,
    lease_expires_at timestamptz,
    heartbeat_at timestamptz,
    progress jsonb,
    progress_revision bigint NOT NULL DEFAULT 0 CHECK (progress_revision >= 0),
    failure_code varchar(64),
    failure_summary varchar(512),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    terminal_at timestamptz,
    CHECK (
        (state = 'running' AND owner_id IS NOT NULL AND lease_token IS NOT NULL
            AND lease_expires_at IS NOT NULL)
        OR
        (state <> 'running' AND owner_id IS NULL AND lease_token IS NULL
            AND lease_expires_at IS NULL)
    ),
    CHECK (
        (state IN ('succeeded', 'failed') AND terminal_at IS NOT NULL)
        OR
        (state IN ('pending', 'running') AND terminal_at IS NULL)
    )
);

CREATE UNIQUE INDEX _chirp_jobs_queue_idempotency_key
    ON _chirp_jobs (queue_name, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX _chirp_jobs_claim_order
    ON _chirp_jobs (queue_name, priority DESC, available_at, created_at, id)
    WHERE state IN ('pending', 'running');

CREATE INDEX _chirp_jobs_expired_leases
    ON _chirp_jobs (queue_name, lease_expires_at, id)
    WHERE state = 'running';
