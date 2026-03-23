-- Premium messages table (kept for DB compatibility)
CREATE TABLE IF NOT EXISTS premium_messages (
    id SERIAL PRIMARY KEY,
    type VARCHAR(20) NOT NULL,
    file_id VARCHAR(255),
    text TEXT,
    caption TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_premium_messages_position ON premium_messages(position);
