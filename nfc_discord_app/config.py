"""Application configuration and constants."""

import os
import logging
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "")

USERS_JSON_PATH: Path = BASE_DIR / "users.json"

COOLDOWN_SECONDS: int = int(os.getenv("COOLDOWN_SECONDS", "5"))

NFC_READER_PATH: str = os.getenv("NFC_READER_PATH", "usb:054c:06c1")

WEBHOOK_TIMEOUT_SECONDS: int = int(os.getenv("WEBHOOK_TIMEOUT_SECONDS", "10"))

STATE_RESET_HOURS: int = int(os.getenv("STATE_RESET_HOURS", "12"))

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

DISCORD_CLIENT_ID: str = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET: str = os.getenv("DISCORD_CLIENT_SECRET", "")
FLASK_SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "default-dev-secret-key")


def get_logger(name: str) -> logging.Logger:
    """Create a configured logger instance."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    return logger


def validate_config() -> list[str]:
    """Validate required configuration values and return a list of errors."""
    errors: list[str] = []
    if not DISCORD_WEBHOOK_URL:
        errors.append("DISCORD_WEBHOOK_URL is not set. Check your .env file.")
    if not USERS_JSON_PATH.exists():
        errors.append(f"users.json not found at {USERS_JSON_PATH}")
    return errors
