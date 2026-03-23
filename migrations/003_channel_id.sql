-- Store channel ID in bot (set via admin panel instead of .env)
ALTER TABLE welcome_config ADD COLUMN IF NOT EXISTS channel_id BIGINT;
