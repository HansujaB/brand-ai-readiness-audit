---
name: crawl-render-audit
description: Audit crawler permissions, public page access, raw-versus-rendered facts, media text extraction and structured-data consistency. Use for machine accessibility and rendering diagnostics.
license: MIT
metadata:
  compatibility: Requires the intact marketplace and Python with requests, beautifulsoup4 and jsonschema. Playwright and pypdf are optional. Anonymous read-only public HTTP(S) evidence only.
---

Own access, indexability, rendering, media extraction and structured-data consistency. Run `python skills/crawl-render-audit/scripts/crawl_check.py URL` from the intact marketplace root. Read [the checklist](references/checklist.md).

Use only the shared collector: it validates public URLs, checks robots before page discovery and each redirect, limits requests/body sizes, caches evidence and enforces the remaining global budget. Search, training and user-triggered access are separate roles. Respect training opt-outs; a training exclusion is not a search visibility defect. A robots file that cannot be retrieved reliably yields unknown permission and no content fetch.

Inspect case-insensitive index directives token by token, preserving crawler scope and repeated header lines. Distinguish bare none from max-image-preview:none. Observe snippet controls, PDF X-Robots-Tag and raw/rendered canonical metadata without assuming publisher intent. A single HTTP error is an observation, not proof of a persistent outage. Missing sitemaps are not defects for small normally linked sites. Validate sitemap and child document roots and use listed URLs for bounded discovery. Count unique final pages; failed attempts and redirect aliases do not consume page slots. Honor the first document base URL.

Compare substantive raw and rendered sections and essential facts with their units and conditions. Exclude boilerplate and script text. Never infer a render gap from framework fingerprints or a text-length percentage. Desktop and mobile browser observations must use the same protected collection layer. Block form submissions, websocket traffic, service workers and non-GET requests. Classify blocked resources: missing document/script/style/data resources invalidate content conclusions; image/font failures invalidate visual conclusions. Uninspected frames are separate coverage. Abort browser redirects that cannot remain inside the interceptor; retain final HTTP evidence and report partial coverage.

Read nested JSON-LD including arrays and `@graph`, and the supported nested microdata/RDFa subset. Preserve repeated properties. Unsupported references/custom prefixes must be unknown, never full semantic validation. Missing schema alone is not a defect; a contextual suggestion may be appropriate. Prioritize malformed or contradictory markup. Only compare offer prices when the visible and structured entities can be aligned; multiple products/variants require review. Identity/sameAs belongs to freshness-corroboration.

Extract text from sampled PDFs when pypdf is available. No extracted PDF text means possible scanned content, not proof that a particular fact is inaccessible. Without visual/OCR verification, mark media locking unknown. An absent target fact plus an image does not prove image locking.

Return compact owner JSON with coverage; retain detailed evidence only via --diagnostics-output. Read the [research and change register](../../docs/crawl-orchestrator-research.md). Tool limitations must never appear as site defects.
