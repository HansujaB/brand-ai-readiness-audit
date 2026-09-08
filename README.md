# brand-ai-readiness-audit

An Agent Skill Marketplace that audits a website for two things at once:

1. **AI discoverability** — will search crawlers and AI assistants (ChatGPT, Perplexity, Claude, etc.) find, correctly read, and trust this brand's facts enough to cite them?
2. **On-site engagement** — once a visitor (human or AI-assistant-driven) actually lands on the page, does the page give them a reason to stay?

Given a URL, the marketplace returns one structured JSON report: findings (each with evidence and a severity) plus prioritized suggested actions, including proactive suggestions that go beyond any defect found.

**Recommend-only.** Every skill in this marketplace is read-only. Nothing here authenticates against, modifies, or rate-abuses the target site, and every crawl step respects `robots.txt`.

## Why four skills instead of one

The decomposition follows a genuine separation of concerns — each skill answers a structurally different question with different evidence sources, rather than splitting arbitrarily:

| Skill | Question it answers | Appendix concepts covered |
|---|---|---|
| `crawl-render-audit` | Can a machine even reach and read this content? | A (crawl access), C (render gap, structured data) |
| `freshness-corroboration` | Would a machine trust and correctly attribute this content? | D (cross-web consensus, entity disambiguation), B (extractability) |
| `engagement-audit` | Does a visitor who arrives have a reason to stay? | Round 2 engagement synthesis (not in the appendix — above-fold clarity, CTA, load, mobile, orientation, help affordance, readability) |
| `audit-orchestrator` (**entrypoint**) | Composes the above three into one report | — orchestration only, no checks of its own |

`crawl-render-audit` and `freshness-corroboration` could theoretically be one "discoverability" skill, but they use genuinely different evidence sources and tools — one is pure structural HTML/HTTP analysis, the other requires live web search and search-result judgment — so keeping them separate lets each stay focused and lets a caller invoke just one if that's all they need (e.g. "just check corroboration for this one fact" doesn't need a crawl audit).

## How the entrypoint composes the others

`audit-orchestrator`:
1. Validates the URL and discovers a small representative page sample (homepage + up to a few key pages: pricing, product, blog, about).
2. Runs `crawl-render-audit`, `freshness-corroboration`, and `engagement-audit` against that shared page list.
3. Merges their findings, de-duplicating overlapping evidence, and assigns stable `F-00N` ids ordered by severity then by fix effort.
4. Adds a small number of proactive, mechanism-grounded suggestions beyond any detected defects.
5. Runs an explicit self-check against the three graded failure modes (false positives, overfitting, padding) before finalizing.
6. Emits one JSON report matching `skills/audit-orchestrator/references/schema.md` — an extension of the contest's minimum schema (adds `category`, `affected_urls`, `confidence`, `effort`, and a `run_metadata` block documenting what was actually audited and which optional capabilities, like a headless browser or web search, were available).

A reference implementation of that composition exists at `skills/audit-orchestrator/scripts/run_audit.py`, which shells out to each sub-skill's own script (`crawl_check.py`, `entity_check.py`, `engagement_check.py`) and merges their output — useful when Python execution and the unzipped marketplace folder are both available. When they aren't, an agent should follow the same procedure by hand using its own fetch/search tools, per each skill's SKILL.md.

## Design notes / how false positives are guarded against

Every check in every skill's SKILL.md is written as a **trigger + an explicit false-positive guard**, because the rubric singles out false positives and overfitting as the two things to actively avoid. The clearest example: the render-gap check never treats "this site uses a JS framework" as a defect by itself — it always requires actually diffing raw HTML against rendered content, because server-rendered/prerendered JS sites are perfectly fine. The same pattern (trigger → guard) repeats for robots.txt disallows on legitimate private paths, single-sourcing of inherently proprietary facts, thin `sameAs` on unambiguous brand names, and dense text for genuinely technical audiences.

We deliberately avoided importing any of the oddly-precise numeric thresholds that show up in some secondary "research" write-ups floating around this space (e.g. a specific millisecond cutoff for page load, or an exact citation-rate percentage by content type) — those numbers aren't independently verifiable, and hard-coding unverifiable precision is itself a false-positive risk on sites that are merely unusual rather than actually broken. Where a check needs a numeric judgment call (e.g. "is this render gap substantial," "is this load time slow"), the relevant script reports the raw evidence and the SKILL.md asks for a materiality judgment relative to the page's own context, not a universal magic number.

## Running it

```bash
python skills/audit-orchestrator/scripts/run_audit.py https://example.com --depth standard
```

`--depth quick|standard|deep` trades off thoroughness against the ~5 minute runtime target. `quick` skips external corroboration search entirely; `standard` samples a handful of key pages; `deep` samples more pages and should only be used when a longer run is acceptable.

Each sub-skill's script can also be run standalone:

```bash
python skills/crawl-render-audit/scripts/crawl_check.py https://example.com
python skills/freshness-corroboration/scripts/entity_check.py https://example.com
python skills/engagement-audit/scripts/engagement_check.py https://example.com
```

Dependencies: `requests`, `beautifulsoup4`, `lxml` (for sitemap XML parsing). `playwright` is optional — the render-gap check in `crawl-render-audit` degrades gracefully to a documented manual fallback if it isn't installed. Cross-web corroboration search and entity-collision search (in `freshness-corroboration`) are not scripted at all — they require a live search tool and are meant to be run by whatever agent invokes this skill, using its own web-search capability.

## Compliance

- Every skill folder is an independently valid `agentskills.io` SKILL.md (name, description, license, etc.).
- `marketplace.json` lists all four skills with exactly one `entrypoint: true`.
- No skill writes to, authenticates against, or rate-abuses the target site.
- All crawling respects `robots.txt`.
- No model weights are bundled; the zip is well under the 50MB limit.
