# mail-to-hero

A small headless service that watches an IMAP inbox for web-form
notification emails and creates the corresponding contact in
[HERO](https://hero-software.de) via the External GraphQL API.

```
   ┌────────────┐  IMAP   ┌───────────────┐  GraphQL  ┌───────────┐
   │ web form   │────────▶│ mail-to-hero  │──────────▶│   HERO    │
   │ mailer     │ Anfrage │  poll loop    │ create_   │ Customer  │
   └────────────┘  von:…  └───────────────┘ contact   └───────────┘
                                  │
                                  ▼
                          /data/state.db (SQLite – idempotency)
```

* Polls the configured IMAP folder on a schedule (`POLL_INTERVAL_SECONDS`).
* Filters by subject prefix (default `Anfrage von:`) – server-side
  `IMAP SEARCH SUBJECT` plus a client-side check.
* Parses bodies in the form mailer's `key:value;` syntax (see below) and
  recovers `partner_notes` as a multi-line trailer.
* Calls `create_contact(findExisting: true, contact: {…})` so duplicates
  on the HERO side are merged automatically.
* Tracks processed `(folder, uid)` tuples in SQLite, so a crashed mid-cycle
  process never duplicates contacts on restart.
* Optionally marks processed emails as `\Seen` on the server.

> Project + logbook entry creation are deliberately **not** implemented
> yet – this service only handles the contact step. The matching mutation
> (`create_project_match`) is available in HERO and can be added once the
> required `customer_id` / `measure_id` mapping is settled.

## Email body format

The web-form mailer produces bodies of this shape:

```
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
```

Every key but `partner_notes` is terminated by `;` followed by a newline.
`partner_notes` consumes everything until the end of the body, including
blank lines and free-text paragraphs. Unknown keys (e.g. `Privat: Privat`)
end up under `payload.extra` for diagnostics, not in the HERO contact.

The subject is `Anfrage von: <Name>` and is used as a fallback name
source if the body has no `first_name` / `last_name`.

## Configuration (env vars)

| Variable | Required | Default | Description |
|---|---|---|---|
| `IMAP_HOST` | yes | – | Mailserver hostname |
| `IMAP_PORT` | no | `993` | – |
| `IMAP_SSL` | no | `true` | Use IMAPS (set `false` for STARTTLS scenarios) |
| `IMAP_FOLDER` | no | `INBOX` | Folder to scan |
| `EMAIL_USER` | yes | – | Login |
| `EMAIL_PASSWORD` | yes | – | Login |
| `SUBJECT_PREFIX` | no | `Anfrage von:` | Subject filter |
| `HERO_API_KEY` | yes | – | HERO External API Bearer token |
| `HERO_GRAPHQL_URL` | no | `https://login.hero-software.de/api/external/v7/graphql` | – |
| `POLL_INTERVAL_SECONDS` | no | `60` | Cadence of the polling loop |
| `DRY_RUN` | no | `false` | If `true`, parse + log but never call HERO |
| `MARK_AS_READ` | no | `true` | Set `\Seen` on processed messages |
| `DB_PATH` | no | `/data/state.db` | SQLite location |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Running locally

```bash
pip install -e .
cp .env.example .env  # edit
mail-to-hero
```

## Docker / docker-compose

A pre-built image is published to GHCR via the `Build & Push Docker Image`
workflow:

```
ghcr.io/mbay-odw/mail-to-hero:latest
```

Drop `docker-compose.yml` into a Portainer stack, set the env vars and
deploy. The service maintains its state on a named volume
(`mail_to_hero_data:/data`).

## Testing

```bash
pip install -e ".[dev]"
pytest
```

The parser test suite covers the canonical sample, CRLF handling,
multi-line `partner_notes`, the subject fallback, and the
"`email` is mandatory" guard.

## Extending

* **Project creation**: add a method in `hero_client.py` that wraps
  `create_project_match(customer_id, measure_id, …)` and call it in
  `_process_one` after a successful contact creation.
* **Different note field**: HERO's `CustomerInput` may expose a
  custom-field path for the form's `partner_notes`. Adjust
  `HeroClient._payload_to_contact_input`.
* **More form fields**: extend `_KNOWN_KEYS` in `parser.py` and surface
  the new fields on `FormPayload`.
