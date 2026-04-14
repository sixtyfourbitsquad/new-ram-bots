# new-ram-bots

Telegram welcome bot — multi-instance deployment.

## Features

- Admin panel in Telegram (add/manage welcome, stats, logs, broadcast)
- Channel join-request handler (optional auto-approve)
- Broadcast queue with progress tracking
- Retention drip automation (`+1h`, `+1d`, `+3d`) per user

## Retention Drip Messages

The bot now schedules follow-up messages automatically after onboarding:

- `1h` after first successful onboarding contact
- `1d` after first successful onboarding contact
- `3d` after first successful onboarding contact

Jobs are stored in PostgreSQL (`retention_drip_jobs`) so they survive restarts.
Each stage is scheduled only once per user.

### Retention env vars

```env
RETENTION_ENABLED=true
RETENTION_1H_MESSAGE=Hey {name}, just checking in. Need help getting started? Reply anytime.
RETENTION_1D_MESSAGE=It has been a day, {name}. Here is a quick reminder to complete your setup.
RETENTION_3D_MESSAGE=3-day reminder, {name}: new updates are waiting. Come back and check them out.
RETENTION_CHECK_INTERVAL_SEC=10
RETENTION_BATCH_SIZE=100
RETENTION_RETRY_DELAY_SEC=300
```

`{name}` is replaced with the user's first name.

## Safe Multi-Bot Deployment Guide (No Data Loss)

Use this checklist every time you deploy a new bot clone on a VPS.

### 1) Isolation rule (most important)

For each bot instance, use:

- a unique Telegram bot token
- a unique domain/subdomain + webhook path
- a dedicated PostgreSQL database (or dedicated schema)
- a dedicated Redis DB index or separate Redis instance
- a dedicated systemd service name

Never share the same DB tables between unrelated bots unless intentionally multi-tenant.

### 2) Create per-bot environment file

Create a `.env` per bot instance with at least:

```env
BOT_TOKEN=...
ADMIN_IDS=123456789
DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/bot_a
REDIS_URL=redis://127.0.0.1:6379/1
WEBHOOK_URL=https://bot-a.example.com
WEBHOOK_PATH=webhook
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8080
LOG_FILE=logs/bot.log
```

Then add optional broadcast/retention vars.

### 3) First deploy / updates

Run:

1. install dependencies (`pip install -r requirements.txt`)
2. start service once (it runs `ensure_tables()` automatically)
3. verify webhook, logs, and `/start` in Telegram

Because tables are created with `IF NOT EXISTS`, startup is idempotent.

### 4) Zero-data-loss backup routine

Before changing VPS, DB credentials, or major bot updates:

- PostgreSQL backup: `pg_dump -Fc <db_name> > backup_<date>.dump`
- Redis backup (if needed for queues/state): `redis-cli --rdb dump_<date>.rdb`
- copy `.env` and logs

Restore test:

- restore DB to a staging database
- start bot with staging `.env`
- verify admin panel and stats

### 5) systemd service per bot (recommended)

Create one unit per bot clone, for example `telegram-bot-a.service`.
Set:

- `WorkingDirectory` to that clone path
- `EnvironmentFile` to that clone `.env`
- `ExecStart` to venv python `run.py`
- `Restart=always`

Use `sudo systemctl restart <service>` for updates and `sudo journalctl -u <service> -f` for logs.

### 6) Safe release flow for every new clone

1. Clone repo to new folder
2. Create venv + install deps
3. Create isolated `.env` (new token/db/redis/webhook)
4. Start service
5. Test `/start`, welcome, join request, broadcast, retention
6. Set channel from admin panel
7. Enable auto-accept only after validation

### 7) Common mistakes to avoid

- Reusing one DB across multiple bots without separation
- Reusing one Redis DB index across clones
- Forgetting to backup before edits/migration
- Changing webhook URL without DNS/SSL ready
