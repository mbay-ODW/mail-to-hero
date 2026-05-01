"""Parser for the web-form email body.

Expected body format (lines, semicolons separate fields):

    first_name:Max;
    last_name:Mustermann;
    street:Musterstraße 12;
    city:Musterstadt;
    zipcode:12345;
    email:max.mustermann@example.com;
    phone_mobile_formatted:015112345678;
    Privat: Privat;
    partner_notes:Neubau, Smart Home, Guten Tag,

    ich interessiere mich für Ihr Angebot.
    Bitte melden Sie sich.

`partner_notes` is special: its value spans the rest of the body (free text
including blank lines), because the form mailer ends the structured part
there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Keys we recognise from the form mailer. Unknown keys are kept under
# `extra` for diagnostics.
_KNOWN_KEYS: set[str] = {
    "first_name",
    "last_name",
    "street",
    "city",
    "zipcode",
    "email",
    "phone_home",
    "phone_mobile",
    "phone_mobile_formatted",
    "company_name",
    "partner_notes",
}

# A line that opens a "key:value" record. Values may continue across lines
# until the next known key or the end-of-body sentinel `;\n`.
_KEY_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*", re.MULTILINE)


@dataclass(frozen=True)
class FormPayload:
    """Cleaned-up content of a single web-form email."""

    first_name: str | None
    last_name: str | None
    email: str | None
    phone_mobile: str | None
    phone_home: str | None
    company_name: str | None
    street: str | None
    city: str | None
    zipcode: str | None
    partner_notes: str | None
    extra: dict[str, str]

    @property
    def has_minimum(self) -> bool:
        """Enough info to create a HERO contact (`email` is mandatory)."""
        return bool(self.email)


def parse_body(body: str) -> FormPayload:
    """Parse a web-form email body into a `FormPayload`.

    Robustness:
      - Tolerates Windows / Unix line endings.
      - Strips trailing semicolons (`first_name:Max;` → `Max`).
      - Treats the `partner_notes:` field as a multi-line "rest of body"
        value, regardless of how many blank lines or commas appear in it.
      - Unknown keys (e.g. `Privat: Privat`) end up in `extra` for logging.
    """
    text = body.replace("\r\n", "\n").strip()
    fields: dict[str, str] = {}

    # Split the body at every "key:" position, keeping the boundaries.
    # Result: [pre_text, key1, value1, key2, value2, …]
    parts = _KEY_LINE.split(text)

    if len(parts) <= 1:
        # No structured content found – return everything as partner_notes.
        return FormPayload(
            first_name=None,
            last_name=None,
            email=None,
            phone_mobile=None,
            phone_home=None,
            company_name=None,
            street=None,
            city=None,
            zipcode=None,
            partner_notes=text or None,
            extra={},
        )

    # Walk pairs (key, value).
    pairs: list[tuple[str, str]] = []
    iterator = iter(parts[1:])
    for key in iterator:
        try:
            value = next(iterator)
        except StopIteration:
            value = ""
        pairs.append((key.strip(), value))

    for index, (key, value) in enumerate(pairs):
        # `partner_notes` consumes everything until end of body (it is the
        # free-text trailer). Stop trimming on `;` for that key – the body
        # may legitimately contain semicolons.
        if key == "partner_notes":
            cleaned = value.strip()
        else:
            # Pre-`partner_notes` keys are terminated by `;` followed by a
            # newline. Take the substring up to the first `;\n` boundary.
            chunk = value
            stop = chunk.find(";\n")
            if stop != -1:
                chunk = chunk[:stop]
            else:
                # Last record before partner_notes/EOF: strip a trailing `;`.
                chunk = chunk.rstrip()
                if chunk.endswith(";"):
                    chunk = chunk[:-1].rstrip()
            cleaned = chunk.strip()
            # If the next pair's key is on the same line as our value, our
            # `_KEY_LINE` regex already split it cleanly – nothing to do.
            del index

        if cleaned == "":
            continue

        # Normalise key spelling. The form sends `Privat` capitalised.
        normalised = key.lower()
        # Aliases
        if normalised == "phone_mobile_formatted":
            fields["phone_mobile"] = cleaned
        elif normalised in _KNOWN_KEYS:
            fields[normalised] = cleaned
        else:
            fields.setdefault("__extra__", "")
            fields["__extra__"] += f"{key}: {cleaned}\n"
            fields[f"_extra_{key}"] = cleaned

    extra = {k.removeprefix("_extra_"): v for k, v in fields.items() if k.startswith("_extra_")}

    return FormPayload(
        first_name=fields.get("first_name"),
        last_name=fields.get("last_name"),
        email=fields.get("email"),
        phone_mobile=fields.get("phone_mobile"),
        phone_home=fields.get("phone_home"),
        company_name=fields.get("company_name"),
        street=fields.get("street"),
        city=fields.get("city"),
        zipcode=fields.get("zipcode"),
        partner_notes=fields.get("partner_notes"),
        extra=extra,
    )


def parse_subject_name(subject: str, prefix: str = "Anfrage von:") -> str | None:
    """Pull the customer name out of an `Anfrage von: <Name>` subject.

    Returns `None` if the subject does not match the expected prefix.
    """
    if not subject:
        return None
    text = subject.strip()
    if text.lower().startswith(prefix.lower()):
        return text[len(prefix) :].strip() or None
    return None


__all__ = ["FormPayload", "parse_body", "parse_subject_name"]
