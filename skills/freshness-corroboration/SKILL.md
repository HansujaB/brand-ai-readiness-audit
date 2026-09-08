---
name: freshness-corroboration
description: Audits whether a brand's key facts are stated in one clearly-quotable sentence (extractability), whether those facts are corroborated by independent third-party sources across the web (cross-web consensus), whether the brand's entity is disambiguated from unrelated things sharing its name, and whether content shows credible staleness signals. Use this skill whenever diagnosing why an AI assistant might state a brand's facts incorrectly, attribute them to a competitor, confuse the brand with something else of the same name, or omit the brand because its claims live in only one unverified place. Called by audit-orchestrator as part of a full AI-readiness audit; can also be used standalone for a fact-corroboration or entity-disambiguation check.
license: MIT
compatibility: Requires a web-search capability (the calling agent's own search tool, since this is external corroboration and cannot be scripted without a search API key) plus read access to the target site's key pages. Read-only throughout — never modifies anything, never authenticates.
allowed-tools: web-search, web-fetch, bash/python-execution
metadata:
  category: discoverability
  covers-appendix: D, B
---

# Freshness & Corroboration Audit

## When to use

Use this after (or alongside) `crawl-render-audit`. Where that skill asks "can a machine reach and read this page at all," this skill asks the next two questions from Appendix B and D: "is the fact stated so plainly a machine could quote it," and "would a machine trust this fact, or does it look isolated / stale / ambiguous." A brand can pass every crawl/render check and still be missing from AI answers because its facts are buried in prose, live nowhere else on the web, or share a name with something more prominent.

Do not use this for structural crawl/render checks (`crawl-render-audit`) or for on-site UX (`engagement-audit`).

## Inputs

- `site_url` (required)
- `target_facts` (required for the extractability and corroboration checks — e.g. "founding year", "HQ address", "return policy window", "CEO name"). If not supplied, infer 3-5 plausible target facts from the page itself (things a person would reasonably ask an AI assistant about this brand) and note that they were inferred, not requested.
- `brand_name` (required for entity disambiguation)

## Procedure

### 1. Extractability (Appendix B)

For each target fact, fetch the relevant page and check: is the fact stated as one self-contained, unambiguous sentence a summarizer could lift verbatim in meaning (not verbatim in wording — see copyright note below), or does understanding it require piecing together multiple paragraphs, following a link, or inferring from context?

- Finding trigger: a fact that is true and present on the site, but requires synthesis across multiple sentences/sections to state confidently.
- **False-positive guard:** a fact that is genuinely complex or conditional (e.g. tiered pricing, region-dependent policy) is not a defect for lacking a single sentence — flag it as "consider adding a plain-language summary sentence" (low/medium) rather than treating necessary complexity as a bug.

### 2. Cross-web corroboration (Appendix D)

For each target fact that is the kind of fact a third party could plausibly also state (founding year, HQ location, leadership names, industry category — generically-verifiable facts), run a small number of external searches for that fact phrased independently of the brand's own wording. Count how many *independent* domains (not the brand's own site, not syndicated copies of the same press release) state the same fact consistent with what the brand's site says.

- Finding trigger: a generically-verifiable fact appears on the brand's own domain and nowhere else independently findable.
- **False-positive guard — important:** this check does NOT apply to facts that are inherently single-source by nature: a company's own return policy, internal pricing, or proprietary specs have no reason to be "corroborated" elsewhere — the brand's own site IS the authoritative source for those. Only apply this check to facts a disinterested third party (a news outlet, directory, review site, Wikipedia) would independently know and might report on. Do not flag single-sourcing on facts where single-sourcing is expected and correct.
- Cap external queries at a small number per fact (e.g. 3-5) to keep runtime reasonable — this check does not need exhaustive search, just enough to distinguish "isolated" from "corroborated."

### 3. Entity disambiguation

Search for the bare `brand_name`. Note whether other prominent, unrelated entities (a different company, a common word, a similarly-named person/place) compete for the same name in search results. Then check the site's own `Organization`/`Person` JSON-LD (if `crawl-render-audit` already extracted it, reuse that) for a populated `sameAs` array linking to Wikidata, Wikipedia, or verified social profiles — the mechanism that lets a system disambiguate.

- Finding trigger: meaningful name collision exists AND `sameAs`/disambiguating signals are absent or thin.
- **False-positive guard:** a distinctive, uncommon brand name with no real collision risk should not be flagged just because `sameAs` is technically minimal — severity should scale with actual collision risk, not treated as a blanket structural requirement.

### 4. Staleness signals

Check for `dateModified` (JSON-LD or visible "Last updated" text) on time-sensitive pages (pricing, product specs, blog posts presented as current). Where present, sanity-check plausibility against the content itself (e.g., a "2024 pricing" page with no updated date on content that references current-year figures).

- Finding trigger: time-sensitive content has no visible/structured freshness signal at all, or has one that appears inconsistent with the content.
- **False-positive guard:** evergreen content (an "About us" history page, a foundational explainer) is not expected to carry a recent `dateModified`, and its absence is not a defect there.

## Output

Return a list of finding objects: `{title, severity, evidence, affected_urls, category: "discoverability", confidence, suggested_action: {summary, priority}}`. Include a `confidence` field here specifically (`high`/`medium`/`low`) because corroboration and entity checks rely on a finite, non-exhaustive search sample — say so honestly rather than presenting a sampled search as definitive. See `references/checklist.md` for severity guidance.
