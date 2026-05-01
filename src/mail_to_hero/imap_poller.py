"""Light-weight IMAP polling helper.

We use the standard library's ``imaplib`` to keep the runtime image small
and avoid an extra dependency. Only the operations needed for our use case
are implemented: SEARCH for matching subjects, FETCH headers + body, and
optionally mark a message ``\\Seen``.
"""

from __future__ import annotations

import email
import imaplib
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import Message

from .config import Config

logger = logging.getLogger(__name__)


@dataclass
class FetchedMessage:
    folder: str
    uid: int
    message_id: str | None
    subject: str
    body: str
    raw: Message


def _decode_header_str(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # pragma: no cover – never let header oddities crash us
        return value


def _extract_text_body(msg: Message) -> str:
    """Return the best plain-text body of an email.message.Message."""
    if msg.is_multipart():
        # Prefer text/plain, fall back to text/html (stripped roughly).
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if ctype == "text/plain" and "attachment" not in disp:
                return _decode_payload(part)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                return _decode_payload(part)
        return ""
    return _decode_payload(msg)


def _decode_payload(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


class ImapPoller:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg

    def fetch_matching(self) -> Iterator[FetchedMessage]:
        """Yield every message whose subject starts with ``cfg.subject_prefix``.

        Connects on demand and disconnects after the loop body finishes.
        Each yielded message has its UID, decoded subject and plain-text
        body ready to use.
        """
        cfg = self._cfg
        cls = imaplib.IMAP4_SSL if cfg.imap_ssl else imaplib.IMAP4
        logger.debug(
            "Connecting to IMAP %s:%s ssl=%s as %s",
            cfg.imap_host,
            cfg.imap_port,
            cfg.imap_ssl,
            cfg.imap_user,
        )
        client = cls(cfg.imap_host, cfg.imap_port)
        try:
            client.login(cfg.imap_user, cfg.imap_password)
            client.select(cfg.imap_folder)

            # Use SUBJECT search for an efficient server-side filter. IMAP
            # SEARCH is case-insensitive and matches substrings.
            typ, data = client.uid("SEARCH", None, "SUBJECT", cfg.subject_prefix)
            if typ != "OK":
                logger.warning("IMAP SEARCH returned %s: %s", typ, data)
                return
            uid_list = (data[0] or b"").split()
            logger.debug("IMAP SEARCH SUBJECT '%s' → %d hits", cfg.subject_prefix, len(uid_list))

            for uid_bytes in uid_list:
                try:
                    uid = int(uid_bytes)
                except ValueError:
                    continue
                typ, fetched = client.uid("FETCH", uid_bytes, "(RFC822)")
                if typ != "OK" or not fetched:
                    logger.warning("FETCH UID=%s failed: %s", uid, typ)
                    continue
                # `fetched` is a list like [(b'1 (RFC822 {N}', b'<bytes>'), b')']
                raw_bytes: bytes | None = None
                for entry in fetched:
                    if isinstance(entry, tuple) and len(entry) >= 2:
                        raw_bytes = entry[1]
                        break
                if raw_bytes is None:
                    logger.warning("FETCH UID=%s returned no body", uid)
                    continue
                msg = email.message_from_bytes(raw_bytes)
                subject = _decode_header_str(msg.get("Subject"))
                # Belt-and-braces: also enforce the prefix client-side.
                if not subject.lower().startswith(cfg.subject_prefix.lower()):
                    continue
                yield FetchedMessage(
                    folder=cfg.imap_folder,
                    uid=uid,
                    message_id=msg.get("Message-Id") or msg.get("Message-ID"),
                    subject=subject,
                    body=_extract_text_body(msg),
                    raw=msg,
                )
        finally:
            try:
                client.close()
            except Exception:  # pragma: no cover
                pass
            try:
                client.logout()
            except Exception:  # pragma: no cover
                pass

    def mark_seen(self, uid: int) -> None:
        """Set the ``\\Seen`` flag on a UID. Best-effort; logs and swallows."""
        cfg = self._cfg
        cls = imaplib.IMAP4_SSL if cfg.imap_ssl else imaplib.IMAP4
        client = cls(cfg.imap_host, cfg.imap_port)
        try:
            client.login(cfg.imap_user, cfg.imap_password)
            client.select(cfg.imap_folder)
            client.uid("STORE", str(uid), "+FLAGS", "(\\Seen)")
        except Exception:
            logger.exception("Could not mark UID=%s as Seen", uid)
        finally:
            try:
                client.close()
            except Exception:  # pragma: no cover
                pass
            try:
                client.logout()
            except Exception:  # pragma: no cover
                pass


__all__ = ["FetchedMessage", "ImapPoller"]
