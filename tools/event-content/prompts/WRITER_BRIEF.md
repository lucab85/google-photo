<!-- Template. Before handing to an agent, replace {WORK_DIR} (the toolkit work_dir), {TOOLKIT} (path to tools/event-content), {BLOG_REPO} and {BRANCH}. -->
# Brief: writing an event post for lucaberton.com from photos

You are writing ONE blog post (or one gallery addition) for Luca Berton's site, based on the photos he took at an event. The repo is {BLOG_REPO} (Astro; posts in src/content/blog/*.mdx; static assets in static/, which is the publicDir).

## Inputs (scratch dir: {WORK_DIR})
- dossiers/<SESSION>.md: the OCR text seen in photos (slide titles, signs, banners) in chronological order (times are UTC), decoded QR links, and the top publishable photos.
- dossiers/<SESSION>.json: machine-readable version (publishable[] and all[]).
- The dossier's "Calendar hints" section: overlapping calendar events. RSVPs: these don't prove attendance on their own.
- img/<TITLE>.jpg: ~2000px copies of every analysed photo. Read them with the Read tool to check details or read slides. Read individual photos only when needed (they're big); prefer contact sheets.
- `{TOOLKIT}/run.sh sheet <SESSION> pub 36` makes a contact sheet of the publishable photos at sheets/<SESSION>-pub.jpg (+ .tsv mapping index -> TITLE). `all` instead of `pub` shows everything (for understanding only, never for publishing).
- `{TOOLKIT}/run.sh export <slug> TITLE=name TITLE=name ... --thumb TITLE` exports chosen photos to static/blog/events/<slug>/<name>.jpg and a 1200x630 thumbnail at static/blog/thumbnails/<slug>.jpg. ALWAYS use this script (it resizes and strips GPS/EXIF). Never copy originals.

## Hard rules
1. **Facts only.** Every factual claim must come from (a) text visible in a photo (OCR or your own reading of the image), (b) the calendar entry, or (c) an existing post in the repo. Never invent quotes, numbers, attendance, Q&A content, who said what, or Luca's feelings and habits. Opinions are fine if clearly framed as Luca's general view on the topic ("My take:"), short, and plausible for a platform/AI/Kubernetes consultant. If a speaker's name or company is not readable on a slide or in the calendar, don't name them ("the speaker", "the Databricks team").
2. **Attendance.** Only write about the event the photos show. If the calendar lists several overlapping events, use the one the photos confirm (branding, slide content, venue).
3. **Privacy.** Publish only photos where `kind` is scene, selfie or crowd and `flags` is empty. Never publish badges, QR-only photos, screens with passwords or WiFi details, private chats, or photos where someone other than Luca is the clear focus (kind=people). Don't name people in a photo's alt text unless they're the speaker on stage and their name appears on the slide or in the calendar. Never mention home, family, GPS coordinates or the hotel.
4. **Enough material or stop.** If the photos plus calendar don't support at least ~350 words of real, specific content (talk titles, slide topics, what was shown), DON'T write a post. Report "insufficient material" with a one-line reason.
5. **No duplicates.** Before creating a post, grep src/content/blog for the event name, date and venue. If a post exists, add a photo section to it instead (and bump `lastModified`) rather than creating a new one.

## Post format (match existing posts, e.g. src/content/blog/neo4j-graphsummit-amsterdam-2025.mdx and kubecon-europe-2026-recap-week-in-photos.mdx)
- Frontmatter: title (<=60 chars), seoTitle (<=60), snippet and description (120–160 chars each), publishDate "2026-10-02", lastModified "2026-10-02", image {src: /blog/thumbnails/<slug>.jpg, alt}, category (one of the existing categories: grep `^category:` across posts and reuse one; prefer "Conferences", "AI", "DevOps", "Platform Engineering", "Open Source"), author "Luca Berton", tags [...], draft: false.
- Body: `import BlogPromoCard from "../../components/BlogPromoCard.astro";` after the frontmatter, NO H1 in the body, ## sections, 4–8 images as `![descriptive alt](/blog/events/<slug>/<name>.jpg)` each followed by an italic one-line caption, an optional 2-column grid `<div class="grid grid-cols-1 sm:grid-cols-2 gap-4 my-6">` (blank lines around the markdown images inside it), a "## Related" list of 2–4 existing posts (verify each slug exists), and `<BlogPromoCard />` at the end.
- Voice: first person (Luca), plain, specific, no hype words ("incredible", "unmatched", "game-changer"), British/neutral English. Throwbacks to 2025 are fine: write in the past tense, and the publishDate stays 2026-10-02.
- Slug: lowercase-hyphenated, include event name + city + year.

## When done
Return: the slug and file path (or "gallery added to <file>"), the list of exported images, and a bullet list of every factual claim with its source (OCR photo TITLE / calendar / existing post). Do NOT git add, commit or push.

## Extra rules (added after reviewing the OCR output)
6. Never publish, link or quote other people's contact details: LinkedIn QR codes or URLs, emails, phone numbers, or "connect with me" slides. Event and company URLs found in QR codes (event pages, company sites, sli.do) may be linked only if they're clearly official and relevant.
7. Edit ONLY your own new post file (or, for a gallery addition, the one target post) and your own static/blog/events/<slug>/ folder + thumbnail. Do NOT edit src/pages/conferences.astro or any other file. The coordinator does that.
8. Speaker names: you may name a speaker only if the name is readable on a slide, banner or the calendar entry, AND the photo shows them presenting that talk. Spell names exactly as on the slide.
