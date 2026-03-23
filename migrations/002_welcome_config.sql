CREATE TABLE IF NOT EXISTS welcome_config (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    video_file_id VARCHAR(255),
    video_caption TEXT,
    apk_file_id VARCHAR(255),
    apk_caption TEXT
);
INSERT INTO welcome_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
