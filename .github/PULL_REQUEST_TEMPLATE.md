# Pull Request

## Constitution review (mandatory five-point checklist)

Every PR must affirmatively check each box against
[`.specify/memory/constitution.md`](../.specify/memory/constitution.md).

- [ ] **Principle I — Local-First & Non-Destructive**
  No required cloud round-trips for the affected code path. Originals are
  never moved or modified. Symlinks default; copy requires explicit
  `--confirm-copy`.
- [ ] **Principle II — Privacy & Consent by Default**
  Only the minimum OAuth scopes are requested. Tokens stay in the OS
  keychain. No analytics or telemetry. No new third-party network call
  without a feature flag.
- [ ] **Principle III — Test-Driven Development (NON-NEGOTIABLE)**
  Tests were written first and observed to fail before implementation.
  `pytest`, `ruff`, `ruff format --check`, and `mypy` all pass locally.
- [ ] **Principle IV — Cross-Platform Parity**
  Windows / Linux / macOS behavior is preserved. Path handling avoids
  hard-coded separators. Symlink fallback is honored. CI matrix is green.
- [ ] **Principle V — Optional Google-Photos Integration Stays Optional**
  Any GP-related code is gated behind `feature_flags.google_photos_enabled`
  and confined to the two designated files. The default install never makes
  a Photos API call.

## What does this change?

<!-- Short description, link to the relevant spec / clarification / FR. -->

## How was it tested?

<!-- Commands run + expected outcomes. -->

## Migration / compatibility notes

<!-- DB migrations, config changes, breaking CLI flags, etc. -->
