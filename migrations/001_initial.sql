-- Welcome messages: type, file_id, text, caption, position
CREATE TABLE IF NOT EXISTS welcome_messages (
    id SERIAL PRIMARY KEY,
    type VARCHAR(20) NOT NULL,
    file_id VARCHAR(255),
    text TEXT,
    caption TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_welcome_messages_position ON welcome_messages(position);

-- Users tracking
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_join_requests INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen);

-- Broadcast history
CREATE TABLE IF NOT EXISTS broadcast_history (
    id SERIAL PRIMARY KEY,
    type VARCHAR(20) NOT NULL,
    content TEXT,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    success_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_broadcast_history_sent_at ON broadcast_history(sent_at);
