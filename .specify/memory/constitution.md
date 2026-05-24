<!--
SYNC IMPACT REPORT
==================
Version change: (uninitialized template) → 1.0.0
Rationale: Initial ratification of the Calendar Photo Organizer constitution.
           No prior versioned principles exist; MAJOR bump establishes the baseline.

Modified principles: N/A (initial ratification)
Added sections:
  - Core Principles (5 principles):
      I.   Data Safety & Non-Destructive Operations (NON-NEGOTIABLE)
      II.  Privacy-First & Local-First
      III. Test-First Discipline (NON-NEGOTIABLE)
      IV.  Scalability by Streaming & Indexed Persistence
      V.   API Honesty & Modular Optional Integrations
  - Engineering Standards (quality, observability, platform support)
  - Development Workflow & Quality Gates
  - Governance

Removed sections: None.

Templates requiring updates:
  - .specify/templates/plan-template.md             ✅ compatible (Constitution Check
                                                       gate is generic and references
                                                       this file; principles map cleanly)
  - .specify/templates/spec-template.md             ✅ compatible (no constitution-specific
                                                       sections needed)
  - .specify/templates/tasks-template.md            ✅ compatible (test-first ordering and
                                                       category model already align)
  - .specify/templates/checklist-template.md        ✅ compatible
  - .github/prompts/speckit.constitution.prompt.md  ✅ no changes required
  - README.md                                       ⚠ pending (project README not yet
                                                       created; must call out Google
                                                       Photos API limitations and
                                                       Takeout-first workflow per
                                                       Principle V when authored)

Follow-up TODOs: None deferred.
-->

# Calendar Photo Organizer Constitution

## Core Principles

### I. Data Safety & Non-Destructive Operations (NON-NEGOTIABLE)

The application MUST never modify, move, overwrite, or delete original media files
or original Google Takeout exports. All organizing operations MUST be additive:
new folders, symlinks, copies, manifests, or app-created cloud albums only.

Rules:

- Every export or integration action MUST support a dry-run mode that produces the
  full planned output (manifests, logs) without touching the filesystem or remote
  services.
- Local album materialization MUST default to symlinks; copies are the documented
  fallback only when the target filesystem does not support symlinks.
- Destructive-looking verbs (delete, overwrite, replace) MUST NOT exist in the
  public API or UI. Rejecting an album clears matches; it does not remove media.
- Any feature that could touch user data outside the app's own working directory
  MUST require explicit per-session user confirmation and MUST be logged.

Rationale: The user has ~100k irreplaceable personal media items. A single bug in
a destructive path is catastrophic and unrecoverable. Non-destructiveness is the
product's foundational trust contract.

### II. Privacy-First & Local-First

The default execution mode MUST keep all media, metadata, calendar events, and
derived data on the user's machine. No telemetry, no analytics, no cloud uploads,
and no third-party network calls beyond Google APIs explicitly authorized by the
user for the current task.

Rules:

- The first-run experience MUST work fully offline once OAuth tokens (if any) and
  the local Takeout archive are present.
- Any feature that transmits user data off the device (Google Photos upload,
  Picker API, future cloud sync) MUST be behind an explicit feature flag that is
  OFF by default and MUST display a clear scope-of-data disclosure in the UI
  before the first call.
- OAuth tokens and API credentials MUST be stored locally (OS keychain where
  available, otherwise a user-owned config file with restrictive permissions).
- Logs MUST NOT include media bytes, full file contents, or OAuth secrets.
  Personally identifying calendar fields (attendees, descriptions) MUST be
  redactable in shareable diagnostic bundles.

Rationale: The user's archive contains decades of private life. Local-first is
both an ethical baseline and an architectural simplifier (no cloud infra for v1).

### III. Test-First Discipline (NON-NEGOTIABLE)

All non-trivial logic MUST be developed test-first. A change is "non-trivial" if
it touches matching, timestamp extraction, deduplication, folder naming,
manifest/CSV generation, export planning, or database schema/migrations.

Rules:

- Red-Green-Refactor MUST be followed: write a failing test, see it fail for the
  right reason, implement, refactor.
- Unit tests are MANDATORY for: timestamp extraction (EXIF, video metadata,
  filename heuristics, Takeout JSON sidecars, conflicting sources), event
  matching (in-event, buffer, all-day, overlap, timezone shifts), duplicate
  detection (hash, filename+size, Photos id), folder-name sanitization, and
  confidence scoring.
- Integration tests are MANDATORY for: end-to-end ingestion of a fixture
  Takeout-like directory, scan resume after interruption, dry-run export, and
  manifest/CSV correctness.
- Tests MUST run on macOS, Windows, and Linux runners. Platform-specific paths
  (symlinks, long paths, case sensitivity) MUST have at least one test on the
  relevant platform.
- A PR that ships untested non-trivial logic MUST be rejected at review.

Rationale: The matching pipeline is heuristic-heavy and operates at 100k+ scale;
silent regressions corrupt user trust in proposed albums. Tests are the only
durable defense.

### IV. Scalability by Streaming & Indexed Persistence

The system MUST scale to 100,000+ media items on a consumer laptop without
loading the full dataset into memory and without re-doing work on every run.

Rules:

- SQLite is the single source of truth for media, events, matches, proposed
  albums, jobs, and errors. Indexes MUST exist on: media capture timestamp,
  media content hash, calendar event start/end, event id, and match status.
- Scanning, matching, and export MUST be incremental: a file whose path, size,
  and mtime are unchanged since last scan MUST NOT be re-hashed or
  re-metadata-extracted.
- Long-running operations (scan, match, export) MUST run as cancellable
  background jobs with persisted progress, support resume after crash or
  interruption, and emit periodic progress events to the UI.
- UI views over large collections (albums, unmatched media, thumbnails) MUST
  paginate or lazy-load. No endpoint or screen may materialize an unbounded
  in-memory list.
- Errors on individual items MUST be recorded to the `errors` table and MUST
  NOT abort the enclosing job.

Rationale: The 100k-item constraint is the headline scale requirement. Naïve
implementations (load-all-into-RAM, re-scan-every-run) will silently fail in
ways the non-technical target user cannot recover from.

### V. API Honesty & Modular Optional Integrations

The product MUST be truthful — in code, UI, and documentation — about what the
current Google Photos API can and cannot do. The primary supported workflow is
Google Takeout import. Google Photos cloud features are optional, scoped, and
isolated.

Rules:

- The Google Photos integration MUST live in a single module
  (`google_photos_optional.py` or equivalent), MUST be behind a feature flag,
  and MUST be removable without affecting the Takeout pipeline.
- The README and in-app help MUST state explicitly that, due to Google Photos
  Library API restrictions effective March 31, 2025, the app cannot freely read
  or reorganize the user's existing Google Photos library; bulk processing
  requires Google Takeout, and cloud-side album creation is limited to
  app-created content and/or Picker-API-selected items.
- The app MUST NOT advertise, attempt, or imply a "full automatic reorganization
  of your existing Google Photos library" capability.
- OAuth scopes requested MUST be the minimum required for the active workflow
  and MUST be presented to the user before consent.

Rationale: Misrepresenting API capabilities sets up data-loss expectations
(e.g., assuming cloud albums will be reshuffled) and creates Google Trust &
Safety risk. Honest scoping also keeps the architecture clean: the Takeout path
is the well-trodden default; cloud is a clearly bounded add-on.

## Engineering Standards

Language, platform, and quality requirements that apply to every change.

- **Language**: Python 3.12+. Type hints are MANDATORY on all public functions,
  module-level functions, and dataclass/model fields. `from __future__ import
  annotations` is permitted.
- **Static analysis**: Code MUST pass the project's configured linter (ruff or
  equivalent) and type-checker (mypy or pyright in `strict` for new modules)
  before merge.
- **Logging**: Structured logging (key=value or JSON) is MANDATORY for
  ingestion, matching, export, and integration modules. Logs MUST include a
  job id when produced inside a background job. `print()` is forbidden outside
  CLI entry scripts.
- **Platform support**: macOS, Windows, and Linux MUST all be supported.
  Filesystem code MUST use `pathlib.Path` and MUST handle case-insensitive
  filesystems, long paths on Windows, and absent symlink permission.
- **UI**: One UI framework is chosen per major version (FastAPI+HTMX or
  Streamlit for v1). Mixing frameworks within a single version is forbidden.
  The UI MUST expose progress, cancellation, and the dry-run/approve gate
  before any export.
- **Performance budget for v1**: a full scan + match of 100k items on a typical
  consumer laptop MUST complete with steady-state memory under ~1 GB and MUST
  be resumable; first-run ingestion may be slow but subsequent incremental
  runs MUST be near-instant for unchanged files.
- **Schema changes**: every database schema change MUST ship with a migration
  and a test that exercises the migration on a populated fixture DB.

## Development Workflow & Quality Gates

How changes flow from idea to merge.

- **Spec-Kit flow**: features follow `/speckit.specify` → `/speckit.clarify`
  (when scope is non-trivial) → `/speckit.plan` → `/speckit.tasks` →
  `/speckit.implement`. The plan's Constitution Check gate MUST pass before
  Phase 0 research and MUST be re-validated after Phase 1 design.
- **Code review**: every PR MUST be reviewed against this constitution. The
  reviewer MUST explicitly confirm:
  1. No destructive paths introduced (Principle I).
  2. No new off-device data flows without a feature-flag + disclosure
     (Principle II).
  3. Tests precede implementation for non-trivial logic (Principle III).
  4. No unbounded in-memory collections or non-resumable long jobs
     (Principle IV).
  5. No overstated Google Photos cloud capability (Principle V).
- **Complexity justification**: any deviation from the principles MUST be
  recorded in the plan's Complexity Tracking section with a stated simpler
  alternative and the reason it was rejected. Unjustified deviations block
  merge.
- **Release readiness**: a release branch MUST pass the full test matrix on
  all three target OSes and MUST include a successful dry-run demo against
  the bundled fixture Takeout sample.

## Governance

This constitution supersedes ad-hoc conventions and prior informal practices
in this repository. Where this document and another guide conflict, this
document wins until amended.

- **Amendment procedure**: amendments are proposed via a PR that edits this
  file together with a Sync Impact Report (see the HTML comment header). The
  PR MUST identify the version bump type (MAJOR/MINOR/PATCH), update any
  templates or documentation listed as affected, and be approved by the
  project maintainer.
- **Versioning policy**: semantic versioning of the constitution itself.
  - MAJOR: a principle is removed, redefined in a backward-incompatible way,
    or its NON-NEGOTIABLE status changes.
  - MINOR: a new principle or section is added, or existing guidance is
    materially expanded.
  - PATCH: clarifications, wording fixes, or non-semantic refinements.
- **Compliance review**: the maintainer SHOULD perform a constitution
  compliance review at least once per release. Findings are recorded as
  follow-up issues and triaged before the next release cut.
- **Runtime guidance**: agent-facing and contributor-facing runtime guidance
  lives in `.github/copilot-instructions.md` and `README.md`. Those documents
  MUST defer to this constitution on principle questions and MUST be updated
  whenever this constitution changes in a way that affects them.

**Version**: 1.0.0 | **Ratified**: 2026-05-23 | **Last Amended**: 2026-05-23
