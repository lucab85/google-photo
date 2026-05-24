# Google Takeout — How to Export Your Photos

Calendar Photo Organizer ingests a local **Google Takeout** export. Takeout is
free, has no third-party rate limits, and gives you the original full-resolution
files plus per-item sidecar JSON metadata.

## 1. Order an export

1. Visit <https://takeout.google.com>.
2. Click **Deselect all**, then tick **Google Photos** only.
3. Click **All photo albums included** if you want to scope the export to a
   subset (e.g. by year). Otherwise leave it as **all**.
4. Click **Next step**.

## 2. Recommended settings

| Setting             | Recommended                                   |
| ------------------- | --------------------------------------------- |
| Delivery method     | **Send download link via email**              |
| Frequency           | **Export once**                               |
| File type           | **.zip**                                      |
| Maximum size        | **50 GB** (Google splits larger exports)      |

Click **Create export** and wait for the email (can take hours to days).

## 3. Extract the archive

1. Download each `.zip` part from the email.
2. Extract all parts into a single folder, e.g. `~/Downloads/Takeout/`.
3. The resulting tree looks like:

   ```text
   Takeout/
     Google Photos/
       Photos from 2024/
         IMG_20240704_180523.jpg
         IMG_20240704_180523.jpg.json   ← sidecar
         ...
       Vacation 2024/
         ...
   ```

## 4. Sidecar JSON

Each media file has a sibling `.json` file with metadata supplied by Google
Photos at the time of upload. The most important fields for matching are:

- `photoTakenTime.timestamp` — Unix epoch seconds, used as the highest-trust
  capture timestamp tier (D-001 waterfall).
- `geoData` — latitude/longitude (not used by matcher today).
- `description` — preserved when uploading via the optional integration.

Sidecar timestamp wins over EXIF on disagreement (per spec assumption).

## 5. Ingest

```bash
cpo scan ~/Downloads/Takeout
```

Progress is reported in real time. The job is resumable — interrupt with
`Ctrl-C` and re-run; previously hashed files are skipped via the
`(path, size, mtime_ns)` shortcut.

## Notes

- **HEIC files** are read using `pillow-heif` (bundled). No conversion is done;
  the original file is preserved verbatim on export.
- **Video files** keep their original codec; capture time falls back to the
  container metadata (`ffprobe` if available) or filename pattern (D-001 tier 4)
  or finally the file's modified-time (tier 5).
- Duplicate paths within the same Takeout export are detected via content hash
  and collapsed into a single media row.
