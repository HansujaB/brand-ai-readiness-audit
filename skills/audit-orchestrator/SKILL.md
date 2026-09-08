---
name: audit-orchestrator
description: Entrypoint for the brand AI-readiness audit. Given a website, runs crawl-render-audit, freshness-corroboration, and engagement-audit, merges their findings into a single fixed-schema report with severity counts and prioritized suggested actions, and adds proactive improvement suggestions beyond any detected defects. Use this skill whenever asked to audit a website's AI discoverability and/or on-site engagement, to explain why a brand isn't showing up in AI assistant answers, or to explain why visitors bounce — this is the skill to invoke first; it calls the other three as needed.
license: MIT
compatibility: Same requirements as its three constituent skills combined — read-only web fetch, optional headless browser, optional web search, optional Python execution. Degrades gracefully if any sub-capability is missing (documents the manual fallback per sub-skill). Never modifies the target site; read-only, no authentication, respects robots.txt.
allowed-tools: web-fetch, web-search, headless-browser (optional), bash/python-execution
metadata:
  category: orchestration
  composes: crawl-render-audit, freshness-corroboration, engagement-audit
---

# Audit Orchestrator (entrypoint)

## When to use

This is the skill invoked directly for "audit this website" / "why isn't [brand] showing up in ChatGPT" / "why do people leave my site" style requests. It doesn't perform any checks itself — its job is orchestration: gather inputs, delegate to the three specialist skills, merge and de-duplicate their findings, assign priorities, and emit one report matching the fixed output schema.

## Inputs

- `site_url` (required): the website to audit.
- `brand_name` (optional, inferred from the site if not given): used by `freshness-corroboration` for entity disambiguation.
- `target_facts` (optional): specific facts the user cares about verifying (pricing, founding year, policies, etc.). If omitted, infer 3-5 reasonable candidates from the homepage.
- `depth` (optional: `quick` | `standard` | `deep`, default `standard`): controls how many key pages get sampled and how many external corroboration queries run, to keep runtime under the ~5 minute target on a typical site. `quick` = homepage only, no external search. `standard` = homepage + up to 4 discovered key pages, capped corroboration search. `deep` = broader page sample, more corroboration queries — use only if the user asks for a thorough audit and is prepared to wait longer.

## Procedure

1. **Normalize and validate the URL.** Confirm it resolves; if not, stop and report that plainly rather than guessing.

2. **Discover key pages.** Fetch the homepage, look for a sitemap (crawl-render-audit's step 2 does this), and pick up to 4 additional representative pages: a product/category page, a pricing page if one exists, one blog/article page, and an about/contact page if distinct. This shared page list is passed to all three sub-skills so their findings reference the same URLs.

3. **Run `crawl-render-audit`** on the page list with any supplied `target_facts`. Collect its findings.

4. **Run `freshness-corroboration`** on the page list with `brand_name` and `target_facts` (reuse any JSON-LD already extracted in step 3 rather than re-fetching where possible). Collect its findings. Respect the `depth` setting for how many external corroboration searches to run.

5. **Run `engagement-audit`** on the homepage and any clear landing/product pages from the list (skip pages like raw blog posts where engagement mechanics are less meaningful, unless `depth` is `deep`). Collect its findings.

6. **Merge and de-duplicate.** Different sub-skills may occasionally surface overlapping evidence (e.g. both crawl-render-audit and freshness-corroboration touching JSON-LD) — merge findings that describe the same underlying defect rather than double-counting them in the severity summary. Assign a stable `id` (e.g. `F-001`, `F-002`, ...) to each finding in the order you present them, ordering by severity (critical → high → medium → low) then by category.

7. **Add proactive suggestions.** Beyond merged defects, add 1-3 suggested actions that would strengthen discoverability or engagement even where no explicit defect was found — grounded in the same mechanisms (Appendix A-F reasoning + engagement synthesis), not generic boilerplate advice. Mark these clearly as proactive (no paired "problem," or `severity: "low"` with a note that it's a strengthening suggestion rather than a fix).

8. **Compute the summary block** — `total_findings` and counts by severity (`critical`, `high`, `medium`; `low` findings still appear in the findings list but the required summary schema only asks for critical/high/medium counts — include `low` too as an extension field for completeness).

9. **Emit the final report** matching the schema in `references/schema.md` (which extends the contest's minimum schema with `category`, `affected_urls`, and `confidence`, plus `effort` on each suggested action, and a top-level `run_metadata` block documenting what depth/pages were actually audited and which optional capabilities — headless browser, web search — were or weren't available, so the reader knows how much confidence to place in the render-gap and corroboration findings specifically).

## Self-check before finalizing (guard against the graded failure modes)

Before emitting the report, walk through this checklist — it exists because the rubric explicitly penalizes these three failure modes:

- **False positives:** for every `high`/`critical` finding, can you point to the specific false-positive guard in the relevant sub-skill's SKILL.md and confirm it doesn't apply here? If a finding only exists because of a framework fingerprint, a stylistic choice, or an inherently single-source fact, downgrade or drop it.
- **Overfitting:** are any findings phrased in a way that only makes sense for one specific site layout you've seen before, rather than the general mechanism? Rewrite toward the mechanism.
- **Padding:** did every sub-skill actually contribute distinct evidence, or did one produce nothing of substance? It's fine for a sub-skill to return zero findings — that's a real, honest result, not a reason to invent filler findings.

## Output

Emit exactly one JSON object matching `references/schema.md`. Do not include prose commentary outside the JSON unless the user explicitly asked for a narrative walkthrough in addition to the structured report — in that case, the JSON still comes first/is still complete on its own, with a short plain-language summary after it.
