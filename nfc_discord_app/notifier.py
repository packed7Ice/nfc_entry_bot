"""Discord webhook notification."""

import requests

from config import get_logger, DISCORD_WEBHOOK_URL, WEBHOOK_TIMEOUT_SECONDS
from registry import UserInfo

logger = get_logger(__name__)


def build_message(user: UserInfo) -> str:
    """Build the notification message based on available user fields."""
    if user.discord_user_id:
        return f"<@{user.discord_user_id}> {user.message}"
    if user.name:
        return f"{user.name} {user.message}"
    return "登録済みユーザーがNFCをタッチしました"


def send_notification(user: UserInfo) -> bool:
    """Send a Discord webhook message. Returns True on success."""
    message = build_message(user)
    payload = {"content": message}

    try:
        resp = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=WEBHOOK_TIMEOUT_SECONDS,
        )
        if resp.ok:
            logger.info("Discord notification sent successfully")
            return True
        else:
            logger.error(
                "Discord webhook returned HTTP %d: %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
    except requests.ConnectionError as exc:
        logger.error("Discord webhook connection error: %s", exc)
        return False
    except requests.Timeout:
        logger.error("Discord webhook request timed out")
        return False
    except requests.RequestException as exc:
        logger.error("Discord webhook request failed: %s", exc)
        return False
