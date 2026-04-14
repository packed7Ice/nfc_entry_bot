"""Entry point — NFC watch loop with cooldown and Discord notification."""

import sys
import time

from config import get_logger, validate_config, COOLDOWN_SECONDS
from registry import UserRegistry, normalize_tag_id
from notifier import send_notification
from nfc_reader import NFCReader

logger = get_logger(__name__)


class CooldownTracker:
    """Prevents duplicate sends for the same tag within a time window."""

    def __init__(self, seconds: int = COOLDOWN_SECONDS) -> None:
        self._seconds = seconds
        self._last_sent: dict[str, float] = {}

    def is_cooled_down(self, tag_id: str) -> bool:
        """Return True if enough time has passed since the last send for this tag."""
        last = self._last_sent.get(tag_id)
        if last is None:
            return True
        return (time.time() - last) >= self._seconds

    def record(self, tag_id: str) -> None:
        """Record the current time as the last send time for a tag."""
        self._last_sent[tag_id] = time.time()


def handle_tag(tag_id_raw: str, registry: UserRegistry, cooldown: CooldownTracker) -> None:
    """Process a single NFC tag detection."""
    tag_id = normalize_tag_id(tag_id_raw)
    logger.info("NFC tag detected: %s", tag_id)

    if not cooldown.is_cooled_down(tag_id):
        logger.info("Cooldown active for %s — skipping", tag_id)
        return

    user = registry.lookup(tag_id)
    if user is None:
        logger.warning("Unregistered tag: %s", tag_id)
        return

    logger.info("Registered user: %s", user.name or "(no name)")
    success = send_notification(user)
    if success:
        cooldown.record(tag_id)


def main() -> None:
    logger.info("=== NFC Discord Notifier starting ===")

    errors = validate_config()
    if errors:
        for err in errors:
            logger.error(err)
        logger.error("Fix the above configuration errors and restart.")
        sys.exit(1)

    registry = UserRegistry()
    cooldown = CooldownTracker()
    reader = NFCReader()

    if not reader.open():
        logger.error("Could not open NFC reader. Is the device connected?")
        sys.exit(1)

    logger.info(
        "Watching for NFC tags (cooldown=%ds). Press Ctrl+C to stop.",
        COOLDOWN_SECONDS,
    )

    try:
        while True:
            reader.wait_for_tag(
                lambda tid: handle_tag(tid, registry, cooldown)
            )
    except KeyboardInterrupt:
        logger.info("Shutting down…")
    finally:
        reader.close()


if __name__ == "__main__":
    main()
