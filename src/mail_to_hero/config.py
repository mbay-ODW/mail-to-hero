"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    # IMAP
    imap_host: str
    imap_port: int
    imap_user: str
    imap_password: str
    imap_ssl: bool
    imap_folder: str

    # Filtering – which subject does the web-form mailer use?
    subject_prefix: str

    # HERO
    hero_api_key: str
    hero_graphql_url: str

    # Behaviour
    poll_interval_seconds: int
    dry_run: bool
    db_path: str
    log_level: str
    mark_as_read: bool

    @classmethod
    def from_env(cls) -> Config:
        cfg = cls(
            imap_host=os.getenv("IMAP_HOST", "imap.example.com"),
            imap_port=int(os.getenv("IMAP_PORT", "993")),
            imap_user=os.getenv("EMAIL_USER", ""),
            imap_password=os.getenv("EMAIL_PASSWORD", ""),
            imap_ssl=_bool("IMAP_SSL", True),
            imap_folder=os.getenv("IMAP_FOLDER", "INBOX"),
            subject_prefix=os.getenv("SUBJECT_PREFIX", "Anfrage von:"),
            hero_api_key=os.getenv("HERO_API_KEY", ""),
            hero_graphql_url=os.getenv(
                "HERO_GRAPHQL_URL",
                "https://login.hero-software.de/api/external/v7/graphql",
            ),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
            dry_run=_bool("DRY_RUN", False),
            db_path=os.getenv("DB_PATH", "/data/state.db"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            mark_as_read=_bool("MARK_AS_READ", True),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("EMAIL_USER", self.imap_user),
                ("EMAIL_PASSWORD", self.imap_password),
                ("HERO_API_KEY", self.hero_api_key),
            )
            if not value
        ]
        if missing:
            raise ValueError("Missing required environment variables: " + ", ".join(missing))
