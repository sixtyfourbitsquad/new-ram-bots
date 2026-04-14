-- Durable retention drip queue (+1h / +1d / +3d)
CREATE TABLE IF NOT EXISTS retention_drip_jobs (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    stage_key VARCHAR(20) NOT NULL,
    message_text TEXT NOT NULL,
    send_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    last_error TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, stage_key)
);

CREATE INDEX IF NOT EXISTS idx_retention_drip_jobs_due
    ON retention_drip_jobs(status, send_at);
