<!-- Template. Replace {WORK_DIR}, {TOOLKIT}, {BLOG_REPO}, {BRANCH} before handing to an agent. -->
# Brief: blog post (or section) from an on-camera interview

The interviews are short videos the site owner recorded for their show at tech events ("Hi friends… please introduce yourself"). The people interviewed knew they were being filmed for publication. Your input is a whisper transcript plus the photos from the same session.

Repo: {BLOG_REPO} (Astro; posts in src/content/blog/*.mdx; assets in static/). Branch: {BRANCH}. Don't switch branches, and don't commit or push.

## Inputs
- {WORK_DIR}/transcripts/<CLIP>.txt (and .json with timestamps): whisper large-v3 output. Expect mis-heard names, products and places (e.g. "YOLA" for Jolla, "Boston" for Brussels, "TubeCon" for KubeCon), and occasional repetition loops. Correct obvious mishearings from context. Verify the spelling of public people, companies and products with a quick web search on official pages. If a name can't be verified, use first name + role/company as stated, or the role only.
- {WORK_DIR}/interviews-catalog.md: the catalogue (event, type, who, topics, existing post).
- {WORK_DIR}/dossiers/<SID>.md: the session the clip belongs to (event context, slide text, publishable photos).
- `{TOOLKIT}/run.sh sheet <SID> pub 36` and `{TOOLKIT}/run.sh export <slug> TITLE=name ... [--thumb TITLE]` for photos (resized, EXIF-free). Use photos taken close to the clip time (match PXL timestamps). Photos where the interviewee posed with the host are OK only if they're `kind` selfie or crowd in the dossier; otherwise use scene or stage photos.

## Rules
1. **Faithful to what was said.** Summarise the interviewee's points in your own words. Direct quotes only when the transcript is clean and the quote is short (≤ 25 words), and quote exactly. Never invent answers, numbers or opinions. Don't put the host's words in the guest's mouth.
2. **No personal data:** no emails, phone numbers or handles spoken in the clip, nothing personal about the guest beyond their professional introduction. Skip anything off-topic or private.
3. **Context and opinions:** product claims made by a vendor are attributed ("according to X, …"). Add 1–2 short "My take:" paragraphs only where the host has relevant expertise (platform engineering, Kubernetes, AI infrastructure, automation).
4. **No duplicates:** grep the blog for the person, company and event. Extend an existing post rather than creating a near-duplicate.
5. Post format as in WRITER_BRIEF.md (frontmatter limits, no H1, BlogPromoCard, Related with verified slugs, publishDate today). An interview post title pattern: "<Name> (<Company>) at <Event>: <topic>".

## Report back
Slug/path, the clips used, the photos exported, every name you corrected (from → to, with source), and any part of a transcript you deliberately left out.
