# Input and report contract

## Website and locale

The positional input is an absolute public HTTP(S) URL. Optional `--country IN --language en` selects one country and language; `--language en-IN` also supplies its region. Use ISO country codes and language tags. No outside-source manifest or web-search option exists.

Without options, resolution uses the starting URL and its redirects, HTML language, `og:locale`, published alternate links and a country domain. A locale selector chooses one compatible published version deterministically, preferring `x-default`, then URL order. The internal evidence records the selection. A generic site publishing no country retains country `null` and the site default/global audience, rather than inventing a country. A missing language is likewise explicit. Ordinary unprefixed pages remain eligible. Conflicting locale paths and document languages are excluded. The requested version must be published by the website; unavailable versions remain an assessment limitation rather than producing mixed-market results.

All network requests stay on the supplied URL's exact origin: scheme, hostname and effective port. Documents also stay within the selected locale; shared assets can use other paths on the same origin. Other domains, subdomains, www aliases and scheme changes are excluded before address validation, including browser assets and redirects of pages or robots.txt. Default ports normalize to the same origin (for example, HTTPS port 443). The internal evidence records the allowed origin. Each permitted request remains robots checked, public-address validated and read-only. Browser direct network access is disabled; Chromium CDP receives the collector's responses, including each checked redirect hop. Unattached worker or frame traffic remains offline.

## Fact questions

`--facts-file facts.json` accepts up to five evaluated question records:

```json
[
  {
    "question": "What does Starter cost and what commitment applies?",
    "source_url": "https://example.com/pricing",
    "terms": ["INR 999", "Starter"],
    "context": {
      "entity": "Starter",
      "value": "INR 999",
      "exceptions": "Available in India only. Billed annually."
    }
  }
]
```

Terms and context are literal website evidence, not words guessed from the question. A string passed through `--facts` has no evidence terms and remains unresolved until evidence supports it. Automatic candidates cover prices, duration policies and selected specification/service patterns. They preserve nearby applicable conditions and distribute questions across pages. Other facts and languages require the skill's source-grounded review procedure.

## Business-owner report

Write one `<company>_report.json` in the current directory, for example `ikea_report.json` or `lifestyle_report.json`. Use `--brand` when provided, otherwise the first accepted page's published site name, then its domain as fallback. The runner normalizes the company name to a safe lowercase filename with underscores and prints that name. The CLI has no output-path or diagnostics-export option. The public contract is [owner.schema.json](owner.schema.json):

- Required top-level fields: `site`, `audited_at`, `summary`, `improvements_summary`, `findings`.
- Summary: `total_findings`, `critical`, `high`, `medium`; include `low` when applicable (zero is also allowed).
- Improvements summary: `total_improvements`, `critical`, `high`, `medium`, `low`. Count only the improvements included in this report, not discarded candidates, and include zeros when none are listed. These counts are separate from confirmed findings.
- Each finding: `id`, `title`, `severity`, `evidence`, `suggested_action`. The action contains `summary`, `priority` and a short `verification` when available. Write two or three concise sentences describing the actual change and affected content, then one sentence explaining how to verify success.
- Optional `pages` on a finding identifies affected pages. Merge repeated instances of the same fix while preserving different causes or entities.
- Optional `improvements` contains up to three prioritized, supported improvements with `summary`, `priority`, a short `evidence` sentence, `page` and a short `verification` when available. These do not increase defect counts.
- Optional `note` is one plain-language sentence only when an assessment limitation changes the conclusion. Zero verified findings must not imply an unassessed website is healthy.

Use brief business language. State what is wrong, where it occurs and what to change. Avoid code dumps, repeated quotations and long explanations. Keep full source spans, confidence, comparison details, detailed verification evidence, browser statistics, request logs and review queues internal. Do not add a coverage object or export another report. The Python `audit()` return value remains detailed for in-memory reasoning and validation against [report.schema.json](report.schema.json).

Validate the actual filename printed by the runner, for example `python skills/audit-orchestrator/scripts/validate_report.py lifestyle_report.json --write` from the marketplace root. This recomputes both priority summaries and assigns sequential finding IDs. No separate validation artifact is created.

## Runtime

There is one full workflow with no depth selector. Collection targets nine initial pages and up to three information follow-ups. Browser work targets three representative pages at desktop and mobile widths. Limits are 400 requests, 20 MB per response, 100 MB decoded downloads and at most 270 work seconds plus bounded supervisor shutdown. `--max-requests`, `--max-response-mb`, `--max-download-mb` and `--budget` adjust these limits. Sitemap discovery has a separate 2 MB allowance; ordinary links come first.

The skill starts a single five-minute deadline before collection and normally gives the runner 210 seconds. All targeted review and final validation must fit the remainder. Do not create extra evidence files or launch a fresh broad audit after the runner finishes. Runtime limitations stay internal except for a short business-relevant note when necessary.
