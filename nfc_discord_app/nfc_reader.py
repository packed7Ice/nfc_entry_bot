"""NFC reader interface for Sony RC-S380 via nfcpy."""

import threading
from typing import Optional, Callable

from config import get_logger, NFC_READER_PATH

logger = get_logger(__name__)

try:
    import nfc  # type: ignore[import-untyped]
    NFC_AVAILABLE = True
except ImportError:
    NFC_AVAILABLE = False
    logger.warning("nfcpy is not installed — NFC reading will not be available")


def _extract_tag_id(tag: "nfc.tag.Tag") -> str:  # type: ignore[name-defined]
    """Extract a hex identifier string from an nfcpy Tag object."""
    identifier: Optional[bytes] = getattr(tag, "identifier", None)
    if identifier is None:
        # FeliCa tags expose idm
        idm = getattr(tag, "idm", None)
        if idm is not None:
            identifier = idm
    if identifier is None:
        return ""
    return identifier.hex().upper()


class NFCReader:
    """Wraps nfcpy to provide a simple tag-reading interface."""

    def __init__(self, path: str = NFC_READER_PATH) -> None:
        self._path = path
        self._clf: Optional["nfc.ContactlessFrontend"] = None  # type: ignore[name-defined]
        self._stop_event = threading.Event()

    def open(self) -> bool:
        """Open the NFC reader. Returns True on success."""
        if not NFC_AVAILABLE:
            logger.error("nfcpy is not installed — cannot open reader")
            return False
        try:
            self._clf = nfc.ContactlessFrontend(self._path)
            self._stop_event.clear()
            logger.info("NFC reader opened: %s", self._clf)
            return True
        except IOError as exc:
            logger.error("Failed to open NFC reader at %s: %s", self._path, exc)
            return False

    def is_stopped(self) -> bool:
        """Return True if stop() has been called."""
        return self._stop_event.is_set()

    def stop(self) -> None:
        """Signal the reader to stop waiting for tags."""
        self._stop_event.set()

    def close(self) -> None:
        """Stop and close the NFC reader."""
        self.stop()
        if self._clf is not None:
            self._clf.close()
            self._clf = None
            logger.info("NFC reader closed")

    def wait_for_tag(self, on_connect: Callable[[str], None]) -> None:
        """Block until a tag is detected, then call on_connect with the tag ID.

        This method blocks until a tag is tapped and released.
        It calls on_connect(tag_id) once per tap.
        Returns early if stop() is called.
        """
        if self._clf is None:
            logger.error("NFC reader is not open")
            return

        if self._stop_event.is_set():
            return

        tag_id_holder: list[str] = []

        def connected(tag: "nfc.tag.Tag") -> bool:  # type: ignore[name-defined]
            tid = _extract_tag_id(tag)
            if tid:
                tag_id_holder.append(tid)
            else:
                logger.warning("Tag detected but could not extract identifier")
            # Return True to keep the tag active until removed
            return True

        def should_terminate() -> bool:
            return self._stop_event.is_set()

        try:
            self._clf.connect(
                rdwr={"on-connect": connected},
                terminate=should_terminate,
            )
        except Exception as exc:
            if not self._stop_event.is_set():
                logger.error("Error during NFC read: %s", exc)
            return

        if tag_id_holder:
            on_connect(tag_id_holder[0])

    def __enter__(self) -> "NFCReader":
        if not self.open():
            raise IOError(f"Failed to open NFC reader at {self._path}")
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
