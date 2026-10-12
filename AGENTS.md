# AGENTS.md

Guide for AI coding agents and contributors working on `tcs-garr`, the CLI for the
HARICA CertManager used by GARR.

## What the client talks to

- The CLI uses the **session API** of the CertManager web frontend (`/api/...`):
  login with email, password and TOTP, then a JWT in `Authorization` plus a
  `RequestVerificationToken` (CSRF) header. It was reverse engineered from the
  browser and is not versioned.
- The **API key API** (`/cm/v1/...`, header `X-API-Key`) is a documented subset for
  Enterprise Admins and Approvers only. It does not cover SSL requests or downloads,
  so it cannot replace the session API.
- To find an endpoint and its payload, read the public frontend bundles:
  `https://cm.harica.gr/dist/<page>-page.js` (e.g. `mydashboard-page.js`,
  `server-certificate-request-page.js`) or `https://cm.harica.gr/dist/<name>.js`
  (e.g. `enterprise-validator-client-authentication-requests.js`). The exact bundle
  of a page is in its HTML, which needs a logged-in session.

## Layout

- `tcs_garr/harica_client.py`: every HTTP call to HARICA. All requests go through
  `__make_api_request`, which handles the CSRF token, 429 retries and `/Error`
  redirects.
- `tcs_garr/commands/`: one module per command. `main.discover_commands()` imports
  every module and instantiates every `BaseCommand` subclass it finds.
  - Modules starting with `_` are skipped: put shared base classes there (see
    `_enterprise_validator.py`).
  - Import a shared base as a module
    (`from tcs_garr.commands import _enterprise_validator`), not by class name, or
    the base class is discovered as a command too.
- `tcs_garr/utils.py`: `UserRole`, `CertificateStatus`, configuration loading.
- `tcs_garr/chain/`: HARICA production roots used to complete certificate chains.

## Development

```bash
poetry install
poetry run ruff check tcs_garr tests
poetry run ruff format tcs_garr tests      # line length 127
poetry run python -m unittest              # tests are unittest, not pytest
poetry run python -m tcs_garr.main --help  # runs the repository code
```

- `poetry run tcs-garr` may run a non-editable copy installed in the virtualenv, not
  the repository code: use `python -m tcs_garr.main` to try changes.
- Tests mock `HaricaClient._HaricaClient__make_post_request` or `session`; build the
  client with `patch.object(HaricaClient, "prepare_client")` to skip the login.
- Conventional commits; commitizen bumps the version in CI. A push on a branch
  creates an `-rc` tag, a merge into `main` releases to PyPI. `docs:` and `ci:`
  commits do not bump.

## Invariants: do not break these

- Existing commands keep their defaults and payloads. New options must be optional
  and default to the previous behavior; pin old payloads with tests.
- `download` and chain completion: the output must stay byte-identical. Check it by
  downloading an existing production certificate with the old and the new code.
- `HaricaClient.uses_user_endpoints()` decides between user and enterprise endpoints
  in `list`, `revoke` and `download`. Adding a role to `UserRole` must not change its
  result.
- Never hide HARICA errors: no `except Exception: continue` that skips data, no
  success message for an operation that was not checked.

## HARICA quirks

- **Pagination**: lists return 20 items per `startIndex`. Use
  `HaricaClient._fetch_all_pages()`. `GetDomainsValidityByGroupId` without
  `startIndex` still returns everything.
- **Status names**: SSL requests use `Cancelled`, S/MIME and Client Authentication
  use `Canceled`. An unknown status gives HTTP 200 with an empty body.
- **429 Too Many Requests**: frequent for Enterprise Admins. Requests are retried up
  to 4 times (honouring `Retry-After`), then `RateLimitError` is raised and `main`
  exits with a clear message.
- **CSRF token**: read once per session and again after each login. A rejected token
  gives a redirect to `/Error`: reads are retried once with a new token, writes raise
  `ErrorPageError` and are never sent twice.
- **Approvals**: you cannot approve your own request. S/MIME email-only requests have
  no review: after mailbox validation they go straight to `Ready`.
- **Revocation reasons**: codes like `4.9.1.1.1.1` (unspecified) come from
  `GetRevocationReasons`; see BR 4.9.1.1 and the HARICA CPS.
- **Domain validation**: enterprise admins can use `3.2.2.4.7` (DNS) or `3.2.2.4.4`
  (email to `admin|administrator|webmaster|hostmaster|postmaster@<domain>`); see
  BR 3.2.2.4.
- **Web pages** (not `/api`): opening a page the account may not see redirects to
  `/Login`, and the login page signs the session out.

## Trying changes against HARICA

- The configuration has a section per environment (`[harica]`, `[harica-stg]`); pass
  `--environment stg` for staging.
- **Staging** (`cm-stg.harica.gr`): writes only on resources you create (test
  requests, API keys, ACME accounts), never on existing ones. Its CA is not chained to
  the production roots, so `download` always reports an incomplete chain there.
- **Production**: read-only.
- `output_folder` may be the relative `harica_certificates/` (git-ignored): test keys
  and certificates end up there.
- Never print or store secrets: passwords, TOTP seeds and codes, JWTs, ACME HMAC keys,
  API key codes. Mask them in logs and recordings.
