# Google Photos API — Post-March-2025 Restrictions

## What changed

In March 2025 Google restricted the Photos Library API:

- Third-party apps can **no longer** read or modify content they did not create.
- The `photoslibrary.readonly`, `photoslibrary.sharing` and full
  `photoslibrary` scopes are no longer granted to new (or most existing) apps.
- App-created albums and uploads (`photoslibrary.appendonly`) are still
  supported, but only items uploaded by **your** app are visible to your app.
- For user-driven selection of pre-existing items, Google now provides the
  **Picker API** — the user explicitly hands the app a batch of items.

## What this project can do

- **Bulk processing**: handled by ingesting a **Google Takeout** export
  locally. No API call is required and there is no cap on volume beyond
  Takeout's own delivery limits.
- **Picker import** (optional, feature-flag gated): the user selects a small
  batch in Google's Picker UI. Bytes are downloaded into
  `<data_dir>/picker-cache/`, content-hashed, and de-duplicated against any
  identical Takeout items already in the database (FR-036, Clarification Q5).
- **App-created album upload** (optional, feature-flag gated): an approved
  album from this project can be re-uploaded to Google Photos as a brand-new
  album, using `photoslibrary.appendonly`. Only items uploaded through this
  flow are visible to the app afterwards.

## What this project cannot do

- Read or reorganize the user's existing Google Photos library in place.
- List albums or items created by the official Google Photos app or other
  third-party apps.
- Delete or modify cloud-side content.
- Bypass quota limits or daily upload caps imposed by Google.

## Non-promises

- We do **not** promise full-library reorganization through the Google Photos
  API. Use Takeout for that workflow.
- We do **not** mirror Picker-imported items back to Google Photos automatically;
  the upload flow is a separate, explicit user action.
- We do **not** retain OAuth refresh tokens outside your OS keychain.

## Configuration

```bash
pip install -e ".[google-photos]"
export CPO_FEATURE_FLAGS__GOOGLE_PHOTOS_ENABLED=true
```

With the flag off (default) **no Google Photos network calls are made**, even
transitively (SC-009, C-HTTP-2). The optional integration is wholly contained
in `src/calendar_photo_organizer/google_photos_optional.py` and
`src/calendar_photo_organizer/ui/routes/google_photos.py` and can be deleted
without affecting the Takeout pipeline (Principle V).
