# Brand AI readiness audit

A website-only Agent Skill Marketplace for one country and language per run. It audits machine access, fact context, consistency between the website's pages, and public visitor journeys. It produces one compact `<company>_report.json` for a business owner: problems, short evidence and prioritized actions. It does not fetch news articles, research outside publishers or modify the website.

| Skill | Responsibility |
|---|---|
| audit-orchestrator | Locale, representative collection, budgets, specialist composition, evidence review and final report |
| crawl-render-audit | Robots/index controls, raw/rendered facts, media and structured data |
| freshness-corroboration | Fact qualifications, website policy/price consistency, dates and organization context |
| engagement-audit | Visitor questions, relevant information paths and desktop/mobile obstacles |

## Run

Keep the entire marketplace together; entrypoint scripts import `auditlib`.

```sh
python -m pip install -r requirements.txt
python -m pip install -r requirements-optional.txt
python -m playwright install chromium
python skills/audit-orchestrator/scripts/run_audit.py https://example.com
```

The browser/PDF dependencies are optional. Use `--no-browser` for static evidence. To choose a particular version and company name:

```sh
python skills/audit-orchestrator/scripts/run_audit.py https://www.lifestylestores.com/in/en/ --brand Lifestyle --country IN --language en
```

A regional starting URL also supplies scope. With neither a country nor language option, the audit resolves one version from the URL, redirects and website metadata/alternate links. It does not assume India. A generic site with no published country remains a single default/global version with country unknown; it still audits ordinary unprefixed pages. Detailed locale selection stays in the internal evidence.

Use `--facts-file` for source-supported questions/qualifications and `--pages` for relevant same-locale pages. See [the input and report contract](skills/audit-orchestrator/references/schema.md). The calling agent reviews important uncertainty within the same five-minute deadline. Detailed analysis stays internal.

## Evidence and resource use

The only delivered file is `<company>_report.json`. It follows the competition minimum: website, audit date, severity counts, and findings with a clear title, short evidence, specific prioritized action and a short verification step. An `improvements_summary` separately counts the listed improvements by priority, including zeros when there are none. Useful affected-page links, up to three improvements and a one-sentence assessment note are optional. Repeated instances requiring the same fix are grouped. There are no coverage objects, diagnostic exports, browser statistics or review queues in the business report. The CLI prints the chosen filename. `--brand` supplies the company name; otherwise the first accepted page's site metadata or structured website/organization name is used, with the domain as fallback. Names are converted to lowercase with underscores: IKEA gives `ikea_report.json`, Lifestyle gives `lifestyle_report.json`.

A URL-only invocation runs the full audit workflow; there is no depth selector. Collection targets up to nine initial pages, with up to three additional public information follow-ups. Browser collection prioritizes three representative pages with desktop and mobile observations. Sampling stops at the available time, request and download limits, and unfinished checks remain internal except for an important assessment note. Default limits are 400 HTTP requests, 20 MB per response, 100 MB decoded downloads and a 270-second work deadline. Normal links precede supplementary, locale-filtered sitemap discovery, which has its own 2 MB allowance. Configure limits with `--max-requests`, `--max-response-mb`, `--max-download-mb` and `--budget`.

Every request stays on the supplied URL's exact origin: scheme, hostname and effective port. This includes pages, browser assets, robots.txt, sitemaps and every redirect hop. Other domains, subdomains and www aliases are excluded before address validation or network access; there is no CDN or advertising-host exception. Shared assets on the same origin may sit outside locale paths. The collector respects robots, validates public addresses, pins connections while retaining TLS hostname verification, and excludes authenticated/transactional actions. Direct Chromium networking is offline; CDP delivers collector responses and checks each redirect. Text, visual, absence and interaction reliability are separate, so a failed decorative image does not discard readable content. Lab timing remains instrumented, not field performance.

Automatic reasoning is bounded. Structured prices require identifiable offers. Policy-duration comparisons retain quoted conditions and distinguish historical/regional differences. Other prose, language nuances, custom interactions and media may require the skill's targeted review. The audit does not measure actual AI citation share, rankings, bounce rates or complete commercial transactions.

The five-minute deadline includes collection, any targeted review and final validation. The skill normally allocates 210 seconds to the runner and uses only the remaining time for review.

Use the actual filename printed by the runner when validating; the example below uses Lifestyle.

## Validate

```sh
python -m unittest discover -s tests -v
python skills/audit-orchestrator/scripts/validate_report.py lifestyle_report.json
```

Tests use offline fixtures and real Chromium with controlled responses. They cover website-only collection, locale selection, bounded discovery, browser redirect enforcement, cache reuse, resource-specific reliability, context loss, policy conflicts, report evidence and deadline recovery. Tests also verify that normal and interrupted runs leave only `<company>_report.json` in the output directory. Regression success does not establish accuracy on every unseen site.

The original competition brief is retained in `ps.md`; the current implementation follows the requested website-only scope. [Research notes](research.md) distinguish source guidance from engineering choices.

Browser origin exclusions are recorded internally with the affected resource. Missing scripts, styles or frames limit the observations that depend on them; exclusions are not automatically treated as harmless. Main-content links precede global navigation during discovery; new page purposes precede repeated samples. Text evidence is retained after navigation timeouts when an observed DOM remains available. English/Hindi absence heuristics do not generate missing-answer advice for other declared languages; those questions remain available for source-grounded skill review.
