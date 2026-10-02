<!-- Paste into Claude Code (opened in the BLOG repo) after `./run.sh all` and `./run.sh videos` have finished.
     Replace {TOOLKIT}, {WORK_DIR}, {BLOG_REPO} first. -->

# Turn the dossiers into blog posts

Toolkit: {TOOLKIT} (run its commands as `{TOOLKIT}/run.sh <cmd>`). Derived data: {WORK_DIR}. Blog repo: {BLOG_REPO}.

1. **Worklist.** Run `{TOOLKIT}/run.sh list`. Every line is an event-like session with its calendar hints.
   Read each `{WORK_DIR}/dossiers/<SID>.md` (header + calendar hints + the first ~15 text lines) and decide what the
   event is, trusting the photos over the calendar. Merge consecutive sessions of the same event. Drop sessions
   that are personal (no slides/badges/stage, only places and food).
2. **Coverage check.** For each event, grep `{BLOG_REPO}/src/content/blog` for its name, venue and date.
   - No post: write a new event post.
   - A post exists without photos: add a gallery to it (never duplicate a post).
   - Rich slides on a reusable technical topic: also plan an evergreen deep dive (check the topic isn't covered).
3. **Fan out.** Create a branch. Launch one background agent per item with the matching template from
   `{TOOLKIT}/prompts/` (WRITER_BRIEF for event posts and galleries, TECH_BRIEF for deep dives, PHOTO_BRIEF for
   adding photos to existing posts), with placeholders filled in, the session IDs, the calendar hints and
   the existing posts to link or avoid.
4. **Review every draft yourself** before committing. Check that each claim traces to a photo, the calendar
   or an existing post; that nothing is invented (Q&A, quotes, feelings, attendance); and that no badges,
   contact details, secrets, internal URLs, third-party close-ups, graffiti or family content appear. Drop
   loosely related photos.
5. **Integrate.** Add the events to the site's conferences page and cross-link companion posts. Run the repo
   validators (`pnpm run validate:seo:source`, `validate:images:staged`, `validate:tables:staged`), commit,
   push and open one PR per batch. Write a short social draft per post.
6. **Disk.** After a Takeout part is fully processed, the derived data in {WORK_DIR} is enough to keep exporting
   images (exports fall back to the analysis copies), so the zip can be removed by the owner. Never delete it yourself.
