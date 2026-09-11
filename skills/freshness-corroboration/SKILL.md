---
name: freshness-corroboration
description: Stress-test extraction of brand facts and compare scoped claims across site pages and a capped external evidence sample. Use for context loss, factual inconsistency and identity ambiguity.
license: MIT
metadata:
  compatibility: Requires the intact marketplace and Python with requests, beautifulsoup4 and jsonschema. Playwright and pypdf are optional. Anonymous read-only public HTTP(S) evidence only.
---

Run `python skills/freshness-corroboration/scripts/entity_check.py URL --brand "Brand" --output findings.json --diagnostics-output evidence.json`.

The standalone script returns compact owner-facing JSON: site, audited_at, summary, findings and a small coverage statement. Detailed claims, checks and request logs belong in the optional diagnostics file. Findings must describe an observed business issue and a concrete next action. No minimum finding count; zero findings does not mean the site is verified.

Automatic freshness checks inspect explicitly dated Product/Offer metadata and explicitly labelled article modification dates. An expired priceValidUntil is a published-metadata problem, not proof an expired promotion can still be purchased. Never recommend extending dates without confirming the underlying offer or a substantive article update. Missing dates, old copyright years, and old publication dates alone are not defects.

Price comparisons require explicit product URLs or global identifiers, preserve variant attributes and SKU, currency and supplied offer conditions. Do not assign a nearby price to the brand or compare different products. Different regions/dates or insufficient scope cannot establish a contradiction. Structured data is one evidence source; its absence is not a freshness defect. Prose policies and rendered-only claims remain unverified by the automatic date checks.

For user-supplied extraction questions, use --facts-file with explicit evidence terms. Automatic generic brand-price questions are disabled in freshness and combined runs; the separate crawl evaluator is unchanged. Supplied context diagnostics stay in the evidence file; this step does not redesign the shared extraction evaluator.

Import capped source manifests with --search-results. The runner performs no live search. Quick depth skips external evidence. Ownership and source group annotations must be researched, not inferred from different URLs; unknown ownership cannot count as independent confirmation. Product identifiers must match before comparing external prices. Lack of sampled corroboration is not a defect. Browser resources are not fetched by the standalone freshness command.

Read [implementation and research](references/freshness-changes.md) for exact functions, supported scope and regression tests. The combined runner uses the same freshness checks. Combined and engagement commands now also emit compact owner JSON; optional diagnostics retain the detailed contract.
