"""User registry backed by a JSON file."""

import json
from pathlib import Path
from typing import Optional

from config import get_logger, USERS_JSON_PATH

logger = get_logger(__name__)


class UserInfo:
    """Represents a registered user entry."""

    def __init__(self, tag_id: str, name: str, discord_user_id: str, message: str) -> None:
        self.tag_id = tag_id
        self.name = name
        self.discord_user_id = discord_user_id
        self.message = message

    def __repr__(self) -> str:
        return f"UserInfo(tag_id={self.tag_id!r}, name={self.name!r})"


def normalize_tag_id(raw_id: str) -> str:
    """Normalize a tag ID to uppercase hex without separators or whitespace."""
    cleaned = raw_id.strip()
    for ch in ("-", ":", " "):
        cleaned = cleaned.replace(ch, "")
    return cleaned.upper()


class UserRegistry:
    """Loads and queries user data from a JSON file."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or USERS_JSON_PATH
        self._users: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            logger.warning("Users file not found: %s — registry is empty", self._path)
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.error("users.json root must be a JSON object")
                return
            self._users = data
            logger.info("Loaded %d user(s) from %s", len(self._users), self._path.name)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse users.json: %s", exc)
        except OSError as exc:
            logger.error("Failed to read users.json: %s", exc)

    def lookup(self, tag_id: str) -> Optional[UserInfo]:
        """Look up a user by normalized tag ID. Returns None if not found."""
        normalized = normalize_tag_id(tag_id)
        entry = self._users.get(normalized)
        if entry is None:
            return None
        return UserInfo(
            tag_id=normalized,
            name=entry.get("name", ""),
            discord_user_id=entry.get("discord_user_id", ""),
            message=entry.get("message", "打刻しました"),
        )

    def reload(self) -> None:
        """Reload the JSON file from disk."""
        self._users.clear()
        self._load()
