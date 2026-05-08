"""NFC reader interface for Sony RC-S380 / RC-S956 via nfcpy."""

import threading
from typing import Optional, Callable

from config import get_logger, NFC_READER_PATHS

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
    """Wraps nfcpy to provide a simple tag-reading interface.

    Tries each path in NFC_READER_PATHS in order and uses the first one that opens.
    """

    def __init__(self, paths: Optional[list[str]] = None) -> None:
        self._paths = paths if paths is not None else NFC_READER_PATHS
        self._clf: Optional["nfc.ContactlessFrontend"] = None  # type: ignore[name-defined]
        self._active_path: Optional[str] = None
        self._stop_event = threading.Event()

    def open(self) -> bool:
        """Try each configured path in order. Returns True on first success."""
        if not NFC_AVAILABLE:
            logger.error("nfcpy is not installed — cannot open reader")
            return False

        for path in self._paths:
            try:
                clf = nfc.ContactlessFrontend(path)  # type: ignore[name-defined]
                self._clf = clf
                self._active_path = path
                self._stop_event.clear()
                logger.info("NFC reader opened at %s: %s", path, clf)
                return True
            except IOError:
                logger.debug("NFC reader not found at %s — trying next", path)

        logger.error("No NFC reader found. Tried paths: %s", self._paths)
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
            logger.info("NFC reader closed (was: %s)", self._active_path)
            self._active_path = None

    def wait_for_tag(self, on_connect: Callable[[str], None]) -> None:
        """Block until a tag is detected, then call on_connect with the tag ID.

        Blocks until a tag is tapped and released, then calls on_connect(tag_id).
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
            raise IOError(f"Failed to open NFC reader. Tried paths: {self._paths}")
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
