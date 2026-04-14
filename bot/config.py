"""Load and validate configuration from environment."""
import os
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _get_env(key: str, default: str | None = None) -> str:
    value = os.getenv(key, default)
    if value is None or value == "":
        raise ValueError(f"Missing required env: {key}")
    return value.strip()


def _get_admin_ids() -> List[int]:
    raw = os.getenv("ADMIN_IDS", "")
    if not raw:
        raise ValueError("ADMIN_IDS is required (comma-separated integers)")
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                ids.append(int(part))
            except ValueError:
                raise ValueError(f"Invalid ADMIN_IDS value: {part}")
    return ids


def _get_bool_env(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value for {key}: {raw!r}")


BOT_TOKEN: str = _get_env("BOT_TOKEN")
ADMIN_IDS: List[int] = _get_admin_ids()
_raw_channel = os.getenv("CHANNEL_ID", "").strip()
CHANNEL_ID: int | None = None
if _raw_channel:
    try:
        CHANNEL_ID = int(_raw_channel)
    except ValueError:
        raise ValueError(f"Invalid CHANNEL_ID (must be integer): {_raw_channel!r}")
DATABASE_URL: str = _get_env("DATABASE_URL")
REDIS_URL: str = _get_env("REDIS_URL")
WEBHOOK_URL: str = _get_env("WEBHOOK_URL").rstrip("/")

WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "webhook").strip()
WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST", "0.0.0.0").strip()
_port = int(os.getenv("WEBHOOK_PORT", "8080"))
if not (1 <= _port <= 65535):
    raise ValueError(f"WEBHOOK_PORT must be 1-65535, got {_port}")
WEBHOOK_PORT: int = _port

# Broadcast rate limit (messages per second)
BROADCAST_RATE_LIMIT: int = int(os.getenv("BROADCAST_RATE_LIMIT", "10"))
LOG_FILE: str = os.getenv("LOG_FILE", "bot.log")

# Retention drip settings
RETENTION_ENABLED: bool = _get_bool_env("RETENTION_ENABLED", True)
RETENTION_1H_MESSAGE: str = os.getenv(
    "RETENTION_1H_MESSAGE",
    "Hey {name}, just checking in. Need help getting started? Reply anytime.",
).strip()
RETENTION_1D_MESSAGE: str = os.getenv(
    "RETENTION_1D_MESSAGE",
    "It has been a day, {name}. Here is a quick reminder to complete your setup.",
).strip()
RETENTION_3D_MESSAGE: str = os.getenv(
    "RETENTION_3D_MESSAGE",
    "3-day reminder, {name}: new updates are waiting. Come back and check them out.",
).strip()
RETENTION_CHECK_INTERVAL_SEC: int = int(os.getenv("RETENTION_CHECK_INTERVAL_SEC", "10"))
RETENTION_BATCH_SIZE: int = int(os.getenv("RETENTION_BATCH_SIZE", "100"))
RETENTION_RETRY_DELAY_SEC: int = int(os.getenv("RETENTION_RETRY_DELAY_SEC", "300"))
