# Crawl & Render Audit — Detailed Checklist

Use this as the field-by-field reference when writing findings. Each row: check → what counts as evidence → what counts as a false positive to avoid.

## 1. Robots access
- Evidence: exact `User-agent:` block and `Disallow:` line that matches an audited path; which named agent(s) it applies to.
- Not a defect: disallows on `/admin`, `/cart`, `/checkout`, `/account`, `/search?`, internal API paths, or anything not in the audited content set.

## 2. Sitemap
- Evidence: HTTP status of `/sitemap.xml` and any `Sitemap:` line in robots.txt; whether it parses as XML; count of URLs found vs. count of key pages matched.
- Not a defect: missing sitemap on a small (<10 page) fully internally-linked site — downgrade to `low`/proactive suggestion.

## 3. HTTP status / indexability
- Evidence: final status code after following redirects; raw `<meta name="robots">` tag content; raw `X-Robots-Tag` header value.
- Not a defect: `noindex` on genuinely non-content utility pages (login, thank-you, internal search results) — only flag it on pages meant to be discovered.

## 4. Render gap
- Evidence: side-by-side counts — words/facts present in raw HTML vs. present in rendered DOM; specific target facts checked individually if supplied.
- Not a defect: framework fingerprint alone (React/Vue/Next/Nuxt markers) with no actual content delta. Always diff, never infer from tooling.

## 5. Non-text-locked facts
- Evidence: the specific fact, the element it's locked in (`<img src=... alt="">`, `<canvas>`, embedded PDF URL), and confirmation there's no adjacent plain-text equivalent.
- Not a defect: purely decorative images; facts that ARE duplicated in visible text near the image/graphic.

## 6. Structured data
- Evidence: which `@type` values are present per page, JSON parse success/failure, presence/emptiness of `sameAs` on Organization/Person.
- Not a defect: absence of a schema type that genuinely doesn't apply to the page (don't expect `Product` schema on a blog post).

## Severity quick-reference
| Trigger | Severity |
|---|---|
| Key content page blocked/4xx/5xx/noindex | critical |
| Fact unreadable without JS or locked in non-text media | high |
| No structured data on an evidently typed page | high |
| Missing sitemap (site >10 pages) | medium |
| Incomplete `sameAs`, minor render gap on non-critical content | medium |
| Missing sitemap (site <10 pages), stylistic-only gaps | low |
