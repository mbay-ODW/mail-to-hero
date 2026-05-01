"""Thin HERO External-API GraphQL client – just enough for create_contact."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Config
from .parser import FormPayload

logger = logging.getLogger(__name__)


_CREATE_CONTACT = """
mutation CreateContact($contact: CustomerInput!) {
  create_contact(findExisting: true, contact: $contact) {
    id
    nr
    email
    first_name
    last_name
    company_name
  }
}
"""


class HeroClient:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._headers = {
            "Authorization": f"Bearer {cfg.hero_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_contact(self, payload: FormPayload) -> dict[str, Any]:
        """Create (or find existing) a HERO contact from a parsed form payload.

        Honours `Config.dry_run`: returns a stub response without contacting
        the API.
        """
        contact = self._payload_to_contact_input(payload)

        if self._cfg.dry_run:
            logger.info("[DRY_RUN] would call create_contact with: %s", contact)
            return {"dry_run": True, "contact": contact}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self._cfg.hero_graphql_url,
                json={"query": _CREATE_CONTACT, "variables": {"contact": contact}},
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()

        if "errors" in data:
            raise RuntimeError(f"HERO GraphQL error: {data['errors']}")
        result = (data.get("data") or {}).get("create_contact") or {}
        logger.info(
            "HERO create_contact OK: id=%s nr=%s email=%s",
            result.get("id"),
            result.get("nr"),
            result.get("email"),
        )
        return result

    @staticmethod
    def _payload_to_contact_input(p: FormPayload) -> dict[str, Any]:
        """Map our FormPayload → HERO `CustomerInput`.

        Field names match the HERO External-API GraphQL schema:
            email, first_name, last_name, company_name,
            phone_home, phone_mobile, partner_notes, source,
            address: { street, city, zipcode }
        """
        contact: dict[str, Any] = {}

        if p.email:
            contact["email"] = p.email
        if p.first_name:
            contact["first_name"] = p.first_name
        if p.last_name:
            contact["last_name"] = p.last_name
        if p.company_name:
            contact["company_name"] = p.company_name
        if p.phone_mobile:
            contact["phone_mobile"] = p.phone_mobile
        if p.phone_home:
            contact["phone_home"] = p.phone_home

        if any((p.street, p.city, p.zipcode)):
            address: dict[str, Any] = {}
            if p.street:
                address["street"] = p.street
            if p.city:
                address["city"] = p.city
            if p.zipcode:
                address["zipcode"] = p.zipcode
            contact["address"] = address

        if p.partner_notes:
            contact["partner_notes"] = p.partner_notes

        # Tag every imported contact so it is visible in HERO that this came
        # from the web-form mailer rather than manual entry.
        contact["source"] = "Webformular (mail-to-hero)"

        return contact


__all__ = ["HeroClient"]
