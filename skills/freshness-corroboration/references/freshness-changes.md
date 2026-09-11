# Freshness change record — 2026-09-10

This is the first incremental implementation step. It improves the freshness skill, including its use by the combined runner. It does not complete every SEO, GEO, engagement or freshness capability in the problem statement.

## Files and functions

| File / function | Change and reason |
| --- | --- |
| auditlib/freshness.py — iso_date | Strict ISO calendar-date validation. Missing, malformed or absent dates cannot establish staleness. |
| has_type | Handles scalar and list schema types without relying on a heading. |
| extract_product_claims | Associates Offer prices with explicit Product URL/global identity, SKU and variant attributes. Normalizes decimal prices; rejects invalid prices, ambiguous currencies and aggregate offers. Resolves Offer @id references. Preserves all supplied offer scope before comparison. No fallback from product identity to brand name. |
| check_freshness | Flags published priceValidUntil dates before the observation calendar date, grouped per page. Medium severity reflects a metadata correction, not an outage or proof a sale can still be purchased. Missing dates are unknown. |
| check_article_dates | Compares explicitly labelled, parseable visible article update dates against dateModified of an Article/BlogPosting/NewsArticle identified as this page. Skips publication dates, competing update dates and other articles. Low severity reflects a metadata inconsistency. Supports ISO and a small set of English full-date forms; other formats remain unknown. |
| compare_product_claims | Reuses existing conservative region/date/conditions and external-source grouping rules with the new identified claims. Replaces vague disagreement messages with source URLs and currency/price values. Differences with missing scope do not become contradictions. |
| prioritize_links | Selects a product/pricing/article/policy/about representative before repeats. Deterministic engineering choice, not a search ranking recommendation. |
| owner_report | Groups repeated root-cause findings, computes matching severity counts, emits only id/title/severity/evidence/suggested_action, plus site/audited_at/summary and small coverage. Raw claim arrays and traces are excluded. No finding quota. |
| auditlib/runner.py — audit | Uses the new freshness extraction/date/comparison functions in standalone and combined runs. Stops automatically generating generic brand-price questions for these paths. Explicit supplied questions retain the shared evaluator. Standalone freshness skips browser asset collection and uses diversified links. Other crawl/engagement behavior is unchanged. |
| runner.py — parse_args / main | Adds --diagnostics-output for optional rich evidence. Existing supervisor/checkpoint validation remains; only standalone freshness projects the final result to compact JSON. Combined output remains detailed until the later output-wide step. |
| auditlib/diagnostics.py — Page.__init__ | Guards already-decomposed styled children when removing a hidden ancestor. Littlebox exposed this parser crash; without the fix collection aborted before freshness ran. |
| freshness-corroboration/SKILL.md and references/checklist.md | Documents executable scope, evidence rules, small output, optional detailed evidence and research-backed limits. |
| scripts/entity_check.py | No source edit needed: its existing main(component='freshness') wrapper now invokes the updated runner. |
| tests/test_freshness.py | Regression pairs for product identity, variants, expiry, malformed values, same-scope disagreements, scope differences, source ownership, article identity/date meaning, compact counts, sample diversity and hidden-element parsing. |
| tests/test_audit.py | External-source integration fixture now supplies explicit Product identity and Offer scope, so it tests supported evidence rather than heading guesses. |

## Research and what it supports

1. [Google Product snippets](https://developers.google.com/search/docs/appearance/structured-data/product-snippet): documents priceValidUntil and notes that an expired value can prevent a product snippet from displaying. Supports checking published expiry metadata; it does not establish lost revenue or actual offer availability.
2. [Google product variants](https://developers.google.com/search/docs/appearance/structured-data/product-variants): distinguishes Product variants and unique identifiers. Supports preserving identity and variant scope before comparing prices. Our exact comparison algorithm is an engineering choice, not a Google-endorsed validator.
3. [Google publication dates](https://developers.google.com/search/docs/appearance/publication-dates): recommends consistent equivalent visible and structured dates and distinguishes page dates from event dates. Supports narrowly scoped article update-date comparisons.
4. [Google Search Central date guidance blog](https://developers.google.com/search/blog/2019/03/help-google-search-know-best-date-for): discusses meaningful article updates and accurate dates. Supports correcting dates to reflect reality, not automatically resetting them.
5. [Google helpful-content guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content): warns against changing dates to suggest freshness without substantial change. Supports no age threshold, no mandatory recent-date finding, and no promised ranking improvement.

Severity choices, output grouping, request allocation and the optional diagnostic file are product/engineering decisions driven by the supplied problem statement: accurate, evidence-backed, actionable findings understandable to a business owner. They are not research claims. The implementation uses existing dependencies only.

## Run

From the repository directory:

```powershell
python skills/freshness-corroboration/scripts/entity_check.py https://littleboxindia.com/ --brand Littlebox --depth standard --output tests/littlebox-freshness.json --diagnostics-output tests/littlebox-freshness-diagnostics.json
python -m unittest discover -s tests -p 'test_*.py' -v
```

## Littlebox observation

The successful standard sample inspected five HTML pages with six requests in about seven seconds: homepage, two product pages, returns policy and about page. It recovered two identified product price claims. No supported offer-expiry dates or comparable labelled article update dates were available, and no independent source manifest was supplied. Therefore zero findings means insufficient evidence for a freshness defect, not that prices, policies or the entire site are current. The JSON marks coverage partial.

## Remaining limits

- This is not complete semantic fact checking: policy prose, stale statistics, arbitrary languages/date formats, rendered-only claims and real assistant retrieval need additional evidence/checks.
- Missing structured data is not a freshness defect. Structured extraction trades recall for reliable product identity in this step.
- External evidence is a capped imported sample. Ownership/group labels remain researcher assertions; no live search is added.
- Supplied question context diagnostics still use the existing shared evaluator and are retained in diagnostics, not promoted into compact freshness findings.
- Superseded by the engagement update: combined audits now emit compact output, and static engagement precedes rendering. Old generated smoke JSON has been removed; the observations above are historical.
