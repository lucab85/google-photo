<!-- Template. Before handing to an agent, replace {WORK_DIR} (the toolkit work_dir), {TOOLKIT} (path to tools/event-content), {BLOG_REPO} and {BRANCH}. -->
# Brief: technical deep-dive post inspired by an event talk

You are writing ONE evergreen technical tutorial for Luca Berton's site (Kubernetes / platform engineering / AI infrastructure consultant and author). The repo is {BLOG_REPO} (Astro; posts in src/content/blog/*.mdx; assets in static/, the publicDir). Branch: {BRANCH}. Don't switch branches. Don't git add, commit or push.

## What makes it valuable
- It solves a real, searchable problem (pick the primary keyword from the topic and put it in the title, the first paragraph and one H2).
- Working, copy-pasteable config and commands, explained line by line where it matters, plus how to verify it worked and common pitfalls.
- Hook: one short paragraph saying the talk at <event> got you thinking about it, linking the existing event recap post (given in your task). Then the tutorial stands on its own. Don't attribute the tutorial's content to the speaker; only cite what the recap post already says about the talk.

## Hard rules
1. **Technical accuracy over everything.** Every config key, CRD field, CLI flag, metric name and default value must be verified against the project's official documentation or source. Use WebFetch on official docs, GitHub READMEs or source (argo-cd.readthedocs.io, kyverno.io, postgresql.org/docs, pgbouncer.org, github.com/getsops/sops, docs.ansible.com / galaxy community.sops, github.com/vllm-project/guidellm, opentelemetry.io). If you can't verify something, leave it out. Note the version you documented (e.g. "tested against Argo CD 2.x docs" or "Kyverno 1.13+"). No invented benchmarks or numbers. Numbers from the event recap may be quoted as "in the talk, …" with a link.
2. Opinions are clearly framed ("My take:") and short.
3. No duplicates: read the existing related posts listed in your task (and grep src/content/blog for the main keyword). Your post must cover a different angle and must link to them where relevant (at least 3 internal links in total, including the event recap; verify each slug exists and isn't `draft: true`).
4. No images are required. If you want one, reuse an existing image already published in static/blog/events/<event-slug>/ (reference its path; don't copy files). Thumbnail: reuse the event recap's thumbnail path in frontmatter `image.src` only if it fits; otherwise reuse a relevant existing image path from that event folder. Don't create new image files.
5. Never include personal data, internal URLs or anything from photos beyond what the event recap post already published.

## Format (match existing posts, e.g. src/content/blog/cloudnativepg-postgresql-kubernetes-operator.mdx)
- Frontmatter: title (<=60 chars, keyword-first), seoTitle (<=60), snippet and description (120–160 chars), publishDate "2026-10-02", lastModified "2026-10-02", image {src, alt}, category (reuse an existing category: grep `^category:`), author "Luca Berton", tags [...], draft: false.
- `import BlogPromoCard from "../../components/BlogPromoCard.astro";` after the frontmatter. NO H1 in the body. ## and ### sections. Code fences with a language. Escape `{` `}` `<` outside code fences (MDX!). A "## Related" list (3–5 verified slugs). `<BlogPromoCard />` at the end.
- 1,200–2,000 words. Plain, direct, first person where natural. No hype words.

## When done
Return: slug and path, the primary keyword, the docs URLs and versions you verified against, the internal links, and any claim you dropped because you couldn't verify it.

## Local testing hygiene (added)
- Allowed: temporary kind clusters (create with a unique name such as `deepdive-<topic>` and ALWAYS delete them at the end), docker containers you start yourself (remove them at the end), venvs under {WORK_DIR}. NEVER touch pre-existing clusters (e.g. `cloud-native-demo`) or any kube context you did not create; restore the original current-context when done. Never push images or call external paid APIs.
- Category values: reuse the exact existing casing (e.g. "DevOps", "AI", "Automation", "Platform Engineering", "database").
