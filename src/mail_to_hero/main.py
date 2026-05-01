"""Entry point – the long-running poll loop."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from dotenv import load_dotenv

from .config import Config
from .hero_client import HeroClient
from .imap_poller import FetchedMessage, ImapPoller
from .parser import parse_body, parse_subject_name
from .store import StateStore

logger = logging.getLogger(__name__)

_stop = asyncio.Event()


def _install_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    def _handle(signum, _frame):  # noqa: ANN001 – stdlib signal callback
        logger.info("Received signal %s, shutting down…", signum)
        loop.call_soon_threadsafe(_stop.set)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle)
        except (ValueError, OSError):  # pragma: no cover – not on main thread
            pass


async def _process_one(
    msg: FetchedMessage,
    cfg: Config,
    hero: HeroClient,
    poller: ImapPoller,
    store: StateStore,
) -> None:
    logger.info(
        "Processing UID=%s subject=%r message_id=%s",
        msg.uid,
        msg.subject,
        msg.message_id,
    )
    payload = parse_body(msg.body)

    # Fallback: if the parser couldn't recover any of the name fields,
    # take what is in the subject ("Anfrage von: <Name>").
    if not payload.first_name and not payload.last_name:
        guessed = parse_subject_name(msg.subject, prefix=cfg.subject_prefix)
        if guessed:
            parts = guessed.split(maxsplit=1)
            new_first = parts[0]
            new_last = parts[1] if len(parts) > 1 else None
            payload = payload.__class__(
                first_name=new_first,
                last_name=new_last,
                email=payload.email,
                phone_mobile=payload.phone_mobile,
                phone_home=payload.phone_home,
                company_name=payload.company_name,
                street=payload.street,
                city=payload.city,
                zipcode=payload.zipcode,
                partner_notes=payload.partner_notes,
                extra=payload.extra,
            )
            logger.info(
                "Used subject fallback for name: first=%r last=%r",
                new_first,
                new_last,
            )

    if not payload.has_minimum:
        logger.warning(
            "UID=%s rejected: no email address in body. Body preview: %r",
            msg.uid,
            msg.body[:200],
        )
        store.mark(
            msg.folder,
            msg.uid,
            message_id=msg.message_id,
            contact_id=None,
            contact_email=None,
            success=False,
            error="missing email",
        )
        return

    try:
        result = await hero.create_contact(payload)
    except Exception as exc:
        logger.exception("UID=%s create_contact failed", msg.uid)
        store.mark(
            msg.folder,
            msg.uid,
            message_id=msg.message_id,
            contact_id=None,
            contact_email=payload.email,
            success=False,
            error=str(exc)[:500],
        )
        return

    contact_id = str(result.get("id", "")) if result else ""
    store.mark(
        msg.folder,
        msg.uid,
        message_id=msg.message_id,
        contact_id=contact_id or None,
        contact_email=payload.email,
        success=True,
    )

    if cfg.mark_as_read and not cfg.dry_run:
        poller.mark_seen(msg.uid)


async def _tick(
    cfg: Config,
    hero: HeroClient,
    poller: ImapPoller,
    store: StateStore,
) -> None:
    """One poll cycle: list matching messages, process unseen ones."""
    found = 0
    processed = 0
    for msg in poller.fetch_matching():
        found += 1
        if store.is_processed(msg.folder, msg.uid):
            logger.debug("UID=%s already processed, skipping", msg.uid)
            continue
        await _process_one(msg, cfg, hero, poller, store)
        processed += 1
    if found:
        logger.info("Cycle done: %d matches, %d processed (rest already known)", found, processed)
    else:
        logger.debug("Cycle done: no matching messages")


async def _main() -> int:
    load_dotenv()
    cfg = Config.from_env()

    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info(
        "mail-to-hero starting host=%s folder=%s subject=%r interval=%ds dry_run=%s",
        cfg.imap_host,
        cfg.imap_folder,
        cfg.subject_prefix,
        cfg.poll_interval_seconds,
        cfg.dry_run,
    )

    store = StateStore(cfg.db_path)
    hero = HeroClient(cfg)
    poller = ImapPoller(cfg)

    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop)

    while not _stop.is_set():
        try:
            await _tick(cfg, hero, poller, store)
        except Exception:
            logger.exception("Poll cycle crashed; will retry after interval")
        try:
            await asyncio.wait_for(_stop.wait(), timeout=cfg.poll_interval_seconds)
        except TimeoutError:
            pass

    logger.info("Bye.")
    return 0


def run() -> None:
    """Synchronous entry point used by the console_script."""
    try:
        sys.exit(asyncio.run(_main()))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    run()
