# Contract — Internal HTTP API (FastAPI, loopback only)

The UI process exposes a small HTTP surface bound to `127.0.0.1`. Every
endpoint is server-rendered HTML except where noted (SSE for progress). HTMX
fragments are returned with `HX-Trigger` headers for cross-pane updates.

## Endpoints

| Method | Path | Returns | Purpose |
|---|---|---|---|
| GET  | `/` | HTML | Dashboard: counters for scanned / matched / unmatched / duplicates / errors. |
| GET  | `/auth/google/start` | 302 → Google | Begin Calendar OAuth (loopback redirect). |
| GET  | `/auth/google/callback` | 302 → `/` | Persist tokens, redirect home. |
| POST | `/auth/google/reauth` | 302 → `/jobs/{id}` | Re-auth from a paused job (FR-042a). |
| GET  | `/albums?band=high\|medium\|low&status=…&page=N` | HTML (paginated) | Album list. |
| GET  | `/albums/{id}` | HTML (paginated items) | Album detail with thumbnails. |
| POST | `/albums/{id}/rename` | HTML fragment | Body `{display_name}`. |
| POST | `/albums/{id}/merge` | HTML fragment | Body `{other_album_id, new_name?}`. |
| POST | `/albums/{id}/split` | HTML fragment | Body `{media_ids:[…], new_name}`. |
| POST | `/albums/{id}/approve` | HTML fragment | Per-album approval. |
| POST | `/albums/{id}/reject` | HTML fragment | Per-album rejection (matches return to Unmatched). |
| POST | `/albums/bulk/approve` | HTML fragment | Body `{band: "high"}` or `{album_ids:[…]}` (Q1). |
| POST | `/albums/bulk/reject` | HTML fragment | Body `{band: "low", empty_only: true}` etc. |
| GET  | `/unmatched?date=YYYY-MM-DD&page=N` | HTML | Unmatched by date. |
| POST | `/match/run` | 202 + Location: `/jobs/{id}` | Start match job. |
| POST | `/scan/run` | 202 + Location: `/jobs/{id}` | Body `{takeout_dir}`. |
| POST | `/calendar/import` | 202 + Location: `/jobs/{id}` | Body `{from, to, calendars[]}`. |
| GET  | `/jobs/{id}` | HTML | Job status page. |
| GET  | `/jobs/{id}/stream` | text/event-stream (SSE) | Live progress events. |
| POST | `/jobs/{id}/cancel` | HTML fragment | Cooperative cancellation. |
| GET  | `/export/preview?target=PATH` | HTML | Dry-run plan summary. |
| POST | `/export/run` | 202 + Location: `/jobs/{id}` | Body `{target, mode, confirm_copy?}`. |
| GET  | `/config` | HTML | Show & edit buffers, multi-album toggle, feature flag. |
| POST | `/config` | 303 → `/config` | Persist config. |
| GET  | `/healthz` | `text/plain "ok"` | Liveness. |

## Cross-cutting headers

- `X-Job-Id` echoed on any response produced inside a job context.
- `HX-Trigger: dashboard-refresh` after album / match / scan / export
  mutations.
- All POST handlers accept `application/x-www-form-urlencoded` (HTMX default)
  and `application/json` (for tests).

## Contract guarantees

- C-HTTP-1: server binds **only** to `127.0.0.1`; binding to `0.0.0.0` is
  forbidden (asserted by contract test).
- C-HTTP-2: `/auth/google/*` endpoints exist regardless of feature-flag
  state; Google **Photos** endpoints (under `/picker/*`, `/gp/*`) are
  registered **only** when `feature_flags.google_photos_enabled = true`
  (contract test C-HTTP-2 verifies `404` when flag is off and `200/302` when
  on).
- C-HTTP-3: every paginated endpoint accepts `page` (1-indexed) and
  `page_size` (default 50, max 200) and never returns more than `page_size`
  items in one response.
- C-HTTP-4: `POST /albums/{id}/approve` on a `rejected` album MUST return
  `409 Conflict`; reject-then-approve flow requires explicit un-reject.
- C-HTTP-5: `POST /export/run` with `mode=symlink` against a target where
  `symlink_supported=false` MUST return `409` with body explaining the
  copy-mode requirement (matches `cpo export` C-CLI-2).
- C-HTTP-6: SSE `/jobs/{id}/stream` emits at least one `progress` event per
  10 s while the job is running and a terminal `completed`/`failed`/
  `paused`/`cancelled` event.
