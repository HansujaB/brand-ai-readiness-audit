# Evidence report and input contract

Owner output for every command follows [owner.schema.json](owner.schema.json). --diagnostics-output preserves the detailed internal contract [report.schema.json](report.schema.json), described below. All commands use the same owner projection.

Required contest fields remain: site, audited_at, summary and findings; each finding retains id, title, severity, evidence and suggested_action.priority. The optional diagnostics add check_id, entity, resource, root_cause, evidence_items, confidence_reason and suggested_action.verification. IDs derive from the stable defect key. Summary counts exclude proactive_suggestions and coverage gaps.

`checks` uses pass, fail, unknown, not_applicable or not_run. Pass means only the named check passed on the sampled evidence. `run_metadata` records actually collected pages, actual capabilities used, observed request log, content hashes, elapsed time and completed stages. `fact_extraction_tests`, `claims`, `claim_comparisons`, `visitor_journeys` and `local_rewrite_tests` retain the diagnostic detail.

Each evidence item contains source_url, representation, quote, locator (optional) and observed_at. A quote is an observed span or a clearly named structured measurement, not an invented answer. Cache hashes support evidence provenance; the report does not embed full page bodies.

## Fact input

`--facts "question"` records a question without inventing evidence terms; it remains unknown unless supported. Supply explicit evidence terms through a fact file. For meaningful question-specific checks, use `--facts-file facts.json` with a JSON array:

```json
[
  {
    "question": "What does Starter cost in India?",
    "source_url": "https://example.com/pricing",
    "terms": ["₹999"],
    "context": {
      "entity": "Starter",
      "value": "₹999",
      "billing_period": "billed annually",
      "region": "India"
    }
  }
]
```

Context values must be literal supported source text. Unobserved context is unknown, not a site defect. The runner selects at most five supplied or inferred questions and discloses when fewer supported candidates exist. Automatic extraction currently targets money and return-policy spans; other site types should supply questions.

## External search sample

The calling agent can search and supply `--search-results sources.json`:

```json
[
  {"url":"https://news.example/story", "ownership":"independent", "group":"original-newsroom", "entity":"Starter"},
  {"url":"https://syndication.example/copy", "ownership":"independent", "group":"original-newsroom", "entity":"Starter"},
  {"url":"https://profile.example/brand", "ownership":"brand", "group":"brand", "entity":"Starter"}
]
```

Ownership is brand, independent or unknown. Use one group for copies of the same reporting. Exact duplicate content fingerprints are additionally collapsed. A distinct domain alone is insufficient. Source URLs are fetched with robots enforcement; supplied snippets are not treated as verification. A capped import is not live search; web_search remains false; imported source coverage is recorded separately. The absence of external corroboration is not a defect. Source independence and semantic entity matching still need researcher review.

## Runtime and limits

The work budget is 270 seconds by default (configurable 1–270). All modes share it; the supervisor allows 10 seconds for graceful completion and a further 10-second shutdown/output reserve. Request cap: 80; decoded body cap: configurable with `--max-response-mb` (default 20 MB); total decoded download budget: `--max-download-mb` (default 100 MB); content redirects: five; PDF pages: twenty. These are operational bounds, not a measured guarantee on all machines. Reports preserve unfinished coverage if the supervisor stops the worker.

Browser lab timing uses intercepted/cache-delivered resources and is not representative field performance. Missing browser/search/OCR is explicit coverage. Training permissions remain distinct from search visibility. The collector implements merged user-agent groups, wildcard/end matching, longest-rule selection and Allow on ties, based on [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html). Crawler roles separate OpenAI search/training/user requests per [OpenAI documentation](https://developers.openai.com/api/docs/bots); Google-Extended and Applebot-Extended are content-use control tokens rather than separate fetching agents. Review this registry when providers change policy.

Download budgets include robots, redirects, sitemaps and browser assets. Cache hits do not consume the budget again. Streaming may observe one additional 16 KiB chunk before a limit is detected. Incomplete bodies are never parsed or rendered: their URL, HTTP status, observed bytes and limit reason are reported. If no complete HTML page is available, dependent stages are not_run and excluded from stages_completed. Defaults are configurable operational allowances, not limits on what constitutes a valid website.

Stage status distinguishes sampled, partial, not_run and not_applicable components. A sampled component is bounded coverage, not proof that the site is healthy. See [the research and change register](../../../docs/crawl-orchestrator-research.md) for source links, limits and regression mapping.
