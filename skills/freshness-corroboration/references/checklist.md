# Freshness & Corroboration — Detailed Checklist

## 1. Extractability
- Evidence: quote (paraphrase in your own report, don't reproduce site text verbatim beyond a short fragment) the passage(s) needed to assemble the fact; note how many sentences/sections had to be combined.
- Not a defect: inherently conditional/tiered facts lacking a single-sentence form.

## 2. Cross-web corroboration
- Evidence: the fact as stated on-site; list of independent domains checked and which did/didn't corroborate; explicitly exclude syndicated copies of the brand's own press release from the "independent" count.
- Not a defect: proprietary/internal facts (pricing, policies, specs) that have no reason to appear elsewhere.
- Scope discipline: 3-5 external queries per fact is plenty; this is a sampling check, not exhaustive verification.

## 3. Entity disambiguation
- Evidence: what else shares the brand name in a plain search; whether `sameAs` exists and what it links to.
- Not a defect: unique/distinctive names with no real collision risk, even with a thin `sameAs`.

## 4. Staleness
- Evidence: presence/absence of `dateModified` or a visible "last updated" marker on time-sensitive pages; any internal inconsistency found (e.g., a date claim in the copy that contradicts the metadata).
- Not a defect: evergreen/historical content lacking a recency marker.

## Severity quick-reference
| Trigger | Severity |
|---|---|
| Generically-verifiable, business-relevant fact with zero independent corroboration | high |
| Real name-collision risk with no disambiguating `sameAs`/schema | high |
| Time-sensitive page (pricing, specs) with no freshness signal at all | medium |
| Fact requires synthesis across sections but is otherwise correct | medium |
| Minor/cosmetic staleness ambiguity, thin but non-critical `sameAs` | low |
