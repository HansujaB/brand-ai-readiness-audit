---
name: crawl-render-audit
description: Audits whether AI/search crawlers can actually reach and read a website's content — robots.txt and noindex rules, sitemap validity, HTTP status of key pages, the gap between raw HTML and JS-rendered DOM, facts locked inside images/canvas/video/PDF with no text equivalent, and JSON-LD structured-data presence and validity. Use this skill whenever auditing why a brand's pages might be invisible to crawlers or why a fact that is visible on-screen to a human might not exist for a machine reader. Called by audit-orchestrator as part of a full AI-readiness audit; can also be used standalone to check crawlability/render-gap/structured-data for one or more URLs.
license: MIT
compatibility: Requires outbound network access to the target site (read-only, GET only). Works with just Python + requests + BeautifulSoup for the raw-HTML checks; the render-gap diff additionally benefits from a headless browser (playwright or selenium) if one is installed, but degrades gracefully to a documented manual fallback if not. No authentication, no writes, no crawling of disallowed paths.
allowed-tools: web-fetch, headless-browser (optional), bash/python-execution
metadata:
  category: discoverability
  covers-appendix: A, C
---

# Crawl & Render Audit

## When to use

Use this skill on any URL (or small set of key URLs — home page, 2-3 representative product/category/pricing pages, one blog/article page) when you need to know whether an automated reader — a search crawler, an AI assistant fetching a page mid-answer, or a training crawler — can get in and correctly read what's there. This is Appendix A ("crawl access") and Appendix C ("how machines read a page") from the underlying research: a fact that's perfectly visible to a person can be structurally invisible to a program, and that failure happens *before* any question of content quality.

Do not use this skill to judge writing quality, persuasiveness, or on-site engagement — that's `engagement-audit`. Do not use it to judge whether a fact is corroborated elsewhere on the web or whether an entity is disambiguated — that's `freshness-corroboration`.

## Inputs

- `site_url` (required): the root domain or a specific page to audit.
- `key_pages` (optional): a short list of additional URLs to sample (product page, pricing page, an article). If not supplied, discover up to 5 candidates from the sitemap or homepage nav links.
- `target_facts` (optional): specific facts to check for text-extractability and non-text locking (e.g. "price of X", "return window", "founding year"). If not supplied, run the structural checks only (skip fact-specific extractability, which `freshness-corroboration` also partially covers).

## Procedure

Run `scripts/crawl_check.py <site_url>` when Python execution is available. It performs steps 1-6 below and prints a JSON list of raw findings. If script execution is not available, perform the same steps manually using your own fetch tool, following the same logic — the script is a convenience, not a requirement.

1. **Robots access.** Fetch `/robots.txt`. Parse it (an `urllib.robotparser`-style parse, or manual line parsing) and check, for each of the general agent (`*`) and the common AI/search agents (`GPTBot`, `ChatGPT-User`, `Google-Extended`, `CCBot`, `PerplexityBot`, `ClaudeBot`, `Applebot-Extended`, `Bingbot`), whether `site_url` and `key_pages` are disallowed. Also extract any `Sitemap:` directive.
   - Finding trigger: any of the checked pages is disallowed for `*` or for a **named AI-relevant agent specifically** (a narrower disallow than `*` is itself informative — it shows deliberate exclusion of AI crawlers while allowing general search).
   - **False-positive guard:** a disallow on `/cart/`, `/account/`, `/checkout/`, admin paths, or other genuinely private/transactional paths is normal hygiene, not a defect. Only flag disallows that cover the actual informational content you were asked to check (home, product, pricing, article pages).

2. **Sitemap presence & validity.** Try `/sitemap.xml` directly and also whatever the robots.txt `Sitemap:` line pointed to. Fetch it, confirm it parses as valid XML (or a valid sitemap index referencing child sitemaps), and spot-check that `key_pages` (or a same-count sample) appear in it or are reachable by following links from pages that do.
   - **False-positive guard:** absence of a sitemap is not automatically a defect for a very small site (under ~10 pages) where crawlers can reach everything via normal links — flag it as `low` severity / a proactive suggestion in that case, not `high`.

3. **HTTP status & indexability of key pages.** For each URL, record the final HTTP status after redirects, and check `<meta name="robots">` / `X-Robots-Tag` header for `noindex` or `nofollow`.
   - Finding trigger: a key informational page returning 4xx/5xx, redirecting somewhere unexpected, or carrying `noindex`.

4. **Render gap (raw HTML vs. rendered DOM).** Fetch the raw HTML with a plain HTTP GET (no JS execution). Separately, if a headless browser is available, render the page and extract the fully-loaded visible text. Diff the two: compute the approximate percentage of visible, human-readable text (and specifically any `target_facts`) that exists in the raw HTML vs. only appears post-render.
   - Finding trigger: a meaningful fraction of substantive content (not boilerplate like cookie banners) is present only after JS execution — this is invisible to any reader that doesn't execute JS, and even readers that do execute JS pay a latency/reliability cost for it.
   - **Critical false-positive guard — this is the check the rubric singles out:** detecting "this site uses React/Vue/a JS framework" is *not* itself a finding. Server-side rendering, static site generation, and prerendering all produce JS-heavy sites whose raw HTML is fine. You must actually diff raw vs. rendered content, not pattern-match on framework fingerprints (script tags, `__NEXT_DATA__`, `data-reactroot`, etc.). If raw and rendered text are substantially the same, this is a pass regardless of what framework is in use.
   - **Manual fallback (no headless browser available):** fetch the raw HTML and read it directly for whether the specific facts you care about (price, spec, hours, address) are present as plain text. If you can independently observe the live page renders that content, but it is absent from the raw HTML fetch, you have your evidence for a render gap without needing a full DOM diff.

5. **Facts locked in non-text media.** Within the raw HTML, look for the target facts (or generically: prices, specs, hours, addresses) that appear to exist only inside `<img>` (without matching alt text or adjacent text), `<canvas>`, `<embed>`, `<video>`, or linked-out as a PDF/scanned document with no HTML text equivalent on the page itself.
   - Finding trigger: a fact that a human can clearly see on the page has no plain-text representation anywhere in the raw HTML or accessible alt/aria text.

6. **Structured data presence & validity.** Extract every `<script type="application/ld+json">` block, confirm each parses as valid JSON, and check whether an appropriate `@type` is present for the page's evident purpose (e.g. `Product`/`Offer` on a product page, `Organization` sitewide, `Article` on a blog post, `FAQPage` where there's an FAQ). For any `Organization` or `Person` schema, check for a `sameAs` array and note whether it's present/populated (full corroboration-strength verification of those links happens in `freshness-corroboration`; here you're just checking the field exists and isn't empty).
   - Finding trigger: a page of an evident type (clearly a product/article/FAQ page to a human) carries no matching structured data, or carries JSON-LD that fails to parse.

For each trigger that fires, record: the specific evidence (what you actually observed — quote the disallow line, the status code, the % text delta, the missing schema type), and assign severity using this rubric:
- `critical`: the informational content is functionally invisible to crawlers entirely (blocked by robots.txt, 4xx/5xx, or noindex on a page meant to be found).
- `high`: content is reachable but a substantial, specific fact is unreadable to a non-JS-executing reader or locked in non-text media, or structured data is entirely absent on a page type where it's expected.
- `medium`: partial/minor render gaps, missing sitemap on a larger site, incomplete (not absent) `sameAs`.
- `low`: everything else worth mentioning as a proactive suggestion rather than a defect.

## Output

Return a list of finding objects (not yet the full report — the orchestrator merges these): `{title, severity, evidence, affected_urls, category: "discoverability", suggested_action: {summary, priority}}`. See `references/checklist.md` for the full field-by-field checklist this maps to, and `scripts/crawl_check.py` for the reference implementation.
