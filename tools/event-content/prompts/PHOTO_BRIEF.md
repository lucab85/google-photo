<!-- Template. Before handing to an agent, replace {WORK_DIR} (the toolkit work_dir), {TOOLKIT} (path to tools/event-content), {BLOG_REPO} and {BRANCH}. -->
# Brief: add event photos to existing technical deep-dive posts

Repo: {BLOG_REPO}, branch {BRANCH}. Don't switch branches. Don't git add, commit or push.
Scratch dir (derived data): {WORK_DIR}

## Goal
Each deep-dive post currently has one reused image. Add **3–5 more real photos** from the talk or event that inspired it: slides that illustrate the concept a section explains, the stage, the room. Place each photo in the section it illustrates, not in a block at the end.

## Tools
- dossiers/<SESSION>.md and .json: OCR text, plus `publishable[]` photos (kind scene/selfie/crowd, no flags).
- `{TOOLKIT}/run.sh sheet <SESSION> pub 48`: contact sheet (sheets/<SESSION>-pub.jpg and .tsv index → TITLE). Read the sheet, then read individual img/<TITLE>.jpg files to check slide content.
- `{TOOLKIT}/run.sh export <post-slug> TITLE=name TITLE=name ...` exports to static/blog/events/<post-slug>/<name>.jpg (resized, EXIF/GPS stripped). ALWAYS use it. No --thumb (keep the existing frontmatter image).

## Rules
1. Only photos from `publishable[]` (or `all[]` entries that are kind scene/selfie/crowd with empty flags). Never badges, QR-only photos, contact slides (emails, LinkedIn, handles), passwords, internal URLs or laptop screens, or third parties in close-up.
   - Zoom into every projected screen: presenters' browser address bars often show private links (Google Slides/Docs/Drive edit URLs, internal dashboards), and terminals can show API keys. Pixelate those areas after export, or pick another photo. OCR misses small URL text, so look with your own eyes.
2. Prefer photos NOT already used in the event's recap post (check `grep -o '/blog/events/[^)]*' <recap>.mdx`). Never duplicate an image already in the same post.
3. Markdown: `![descriptive alt](/blog/events/<post-slug>/<name>.jpg)` followed by an italic caption such as `*A slide from <talk> at <event>: <what it shows>.*`. The caption describes what's on the slide. Don't attribute the tutorial's advice to the speaker, and don't name anyone unless the recap already names them as the speaker of that talk.
4. Don't change the technical content. Only add the images and captions, plus `lastModified: "2026-10-02"`. Keep the MDX valid (blank lines around images; no stray `{` `<`).
5. If no fitting publishable photo exists for a post, say so and add none.

## Report back
For each post: the images added (TITLE → name → section), and anything you skipped and why.
