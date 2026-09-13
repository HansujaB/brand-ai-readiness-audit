---
name: crawl-render-audit
description: Inspect crawler access, index controls, raw and rendered facts, media and structured data on the selected website locale. Use to diagnose machine-readability failures with source evidence.
license: MIT
metadata:
  compatibility: Python with requests, beautifulsoup4 and jsonschema. Optional Chromium/Playwright and pypdf. Keep the whole marketplace together. Public website access only.
allowed-tools: Read Write Bash
---

Run `python skills/crawl-render-audit/scripts/crawl_check.py URL` for a standalone audit; it writes only `<company>_report.json`. The orchestrator already invokes these checks during a full audit. Use [the checklist](references/checklist.md) for evidence decisions.

1. Keep every request on the supplied URL's exact origin (scheme, hostname and effective port), including browser assets, robots.txt and redirects. Exclude other domains, subdomains and www aliases before network access; no host-list or CDN exceptions. Use the orchestrator's country/language scope for documents. Prefer normal public links to expensive sitemap discovery. Filter sitemap children by origin and locale before downloading; discovery has a separate 2 MB allowance. A missing or oversized sitemap is not evidence that normally linked pages are inaccessible.
2. Establish access separately for the audit agent and each search crawler. Record exact robots rules, HTTP/index/snippet directives and canonical declarations. Search and training permissions have different purposes. A training opt-out is not a search defect. Intentional exclusions require an intent-qualified action.
3. Compare important facts in raw accessible text with observed rendered content. Preserve headings, table headers, units and qualifying conditions. Use a concrete visitor question; text-length changes and framework names do not establish missing facts. A visible fact can remain valid evidence after an unrelated image failure. Missing text requires a complete enough sample to support absence.
4. Inspect each browser sample's text, visual, absence and interaction reliability separately. Check blocked resource types and the affected element before drawing a conclusion. Chromium's direct network is offline; the collector supplies permitted responses through CDP, including each redirect hop. Unattached worker/frame traffic cannot bypass the collector. Track incomplete areas internally and retain unaffected observations.
5. Inspect JSON-LD, supported microdata/RDFa and visible values for the same entity. Missing markup is only a contextual opportunity; specify the actual page type and visible facts that suitable markup would describe. A canonical conflict, malformed published markup or aligned contradictory value can be a defect. Variants and conditional offers need scope review.
6. For important information in a PDF or image, inspect available extracted text. If a target fact is unavailable, use visual/OCR evidence only when the environment provides it. Recommend an accessible equivalent for an observed media barrier; do not infer image locking merely from an image's presence.

Keep detailed source evidence, verification steps and unresolved comparisons internal. In `<company>_report.json`, give each defect a clear title, severity, short evidence sentence and specific action. Follow the orchestrator's compact report contract and original deadline. Preserve robots and public-network protections during follow-up.
