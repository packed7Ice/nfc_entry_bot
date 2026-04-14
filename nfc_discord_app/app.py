"""Entry point — NFC watch loop with cooldown, state toggle, and Discord notification."""

import sys
import time

from config import get_logger, validate_config, COOLDOWN_SECONDS, STATE_RESET_HOURS
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


class StateTracker:
    """Tracks IN/OUT state per tag, with automatic timeout reset."""

    def __init__(self, reset_hours: int = STATE_RESET_HOURS) -> None:
        self._reset_seconds = reset_hours * 3600
        self._states: dict[str, tuple[str, float]] = {}  # tag_id -> (state, timestamp)

    def toggle(self, tag_id: str) -> str:
        """Toggle the state for a tag and return the new direction ('in' or 'out')."""
        current = self._get_state(tag_id)
        new_state = "out" if current == "in" else "in"
        self._states[tag_id] = (new_state, time.time())
        return new_state

    def _get_state(self, tag_id: str) -> str:
        """Get the current state, resetting to 'out' if expired."""
        entry = self._states.get(tag_id)
        if entry is None:
            return "out"
        state, timestamp = entry
        if (time.time() - timestamp) >= self._reset_seconds:
            return "out"
        return state

    def get_display_state(self, tag_id: str) -> str:
        """Get a human-readable label for the current state."""
        return self._get_state(tag_id).upper()


import threading
from web_app import create_app, events

def handle_tag(
    tag_id_raw: str,
    registry: UserRegistry,
    cooldown: CooldownTracker,
    state: StateTracker,
) -> None:
    """Process a single NFC tag detection."""
    tag_id = normalize_tag_id(tag_id_raw)
    logger.info("NFC tag detected: %s", tag_id)

    if not cooldown.is_cooled_down(tag_id):
        logger.info("Cooldown active for %s — skipping", tag_id)
        return

    user = registry.lookup(tag_id)
    if user is None:
        logger.warning("Unregistered tag: %s", tag_id)
        events.emit("unregistered", {"tag_id": tag_id})
        return

    direction = state.toggle(tag_id)
    label = "入室" if direction == "in" else "退室"
    logger.info("%s: %s (%s)", label, user.name or "(no name)", tag_id)

    success = send_notification(user, direction)
    if success:
        cooldown.record(tag_id)
    
    events.emit("touch", {"tag_id": tag_id, "name": user.name, "direction": direction})


def nfc_worker(reader: NFCReader, registry: UserRegistry, cooldown: CooldownTracker, state: StateTracker) -> None:
    """Background thread to watch for NFC tags."""
    logger.info(
        "Watching for NFC tags (cooldown=%ds, state reset=%dh).",
        COOLDOWN_SECONDS,
        STATE_RESET_HOURS,
    )
    while not (hasattr(reader, "_stop_event") and reader._stop_event.is_set()):
        reader.wait_for_tag(
            lambda tid: handle_tag(tid, registry, cooldown, state)
        )


def main() -> None:
    logger.info("=== NFC Discord Notifier (Web UI) starting ===")

    errors = validate_config()
    if errors:
        for err in errors:
            logger.error(err)
        logger.error("Fix the above configuration errors and restart.")
        sys.exit(1)

    registry = UserRegistry()
    cooldown = CooldownTracker()
    state = StateTracker()
    reader = NFCReader()

    if not reader.open():
        logger.error("Could not open NFC reader. Is the device connected?")
        sys.exit(1)

    app = create_app(registry)

    # Start NFC background thread
    t = threading.Thread(target=nfc_worker, args=(reader, registry, cooldown, state), daemon=True)
    t.start()

    logger.info("Starting Flask server on http://localhost:5000")
    
    import signal
    def signal_handler(sig: int, frame: object) -> None:
        logger.info("Ctrl+C pressed. Shutting down…")
        reader.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        # Run Flask server (blocks main thread)
        app.run(host="127.0.0.1", port=5000, threaded=True)
    finally:
        reader.close()


if __name__ == "__main__":
    main()
