---
name: audit-orchestrator
description: Entrypoint for evidence-driven website AI-readiness audits. Composes access, fact-context, claim-comparison and visitor-journey checks into one prioritized report with explicit coverage.
license: MIT
metadata:
  compatibility: Requires the intact marketplace and Python with requests, beautifulsoup4 and jsonschema. Playwright and pypdf are optional. Anonymous read-only public HTTP(S) evidence only.
---

Use this first for a full audit. Keep all four skill folders and the root `auditlib` package together when running the Python scripts. Read [the report contract](references/schema.md) for output semantics.

Run `python skills/audit-orchestrator/scripts/run_audit.py URL --brand "Brand" --depth standard` from the marketplace root. Optional inputs are `--facts-file`, `--facts`, `--pages`, `--search-results`, `--no-browser`, `--budget` and `--output`. Add --diagnostics-output for detailed evidence. Every command emits compact owner JSON; use --diagnostics-output for the detailed evidence report.

Normalize public HTTP(S) URLs; collect only anonymous GET evidence through the shared collector. Check robots before discovery and every redirected content/resource request. Never fetch disallowed, private, transactional or authenticated paths. The audit crawler has its own user agent; do not impersonate a permitted crawler to bypass exclusions.

Use the shared cache and one 270-second work budget for the entire run, including browser requests and external sources. Reserve allowances for collection, public engagement paths and external evidence; give unused time to rendering. Execute independent page checks in isolation and checkpoint completed evidence before new I/O and after each browser sample. The CLI preserves the last valid checkpoint even if worker cleanup fails. Coverage includes every selected component. Quick/standard/deep sample at most 1/5/9 pages; deep increases breadth within the same budget. Actual completion time still needs benchmarking.

Pass the brand and 3–5 fact questions to the specialist checks. If automatic inference produces fewer supported questions, report the gap rather than invent facts. Preserve headings, table headers and qualifying context. External search needs the calling agent's search tool: sample up to five sources in standard mode or ten in deep mode, group syndication and ownership, and import the manifest documented in the report contract. Do not silently report that live search ran when only an imported sample was processed.

Merge defects by check ID, entity, resource and root cause, combining evidence. Sort by severity then effort; content-derived IDs stay stable across ordering changes. Keep proactive suggestions separate from defects and severity counts. Validate internal diagnostics against `references/report.schema.json` and owner output against `references/owner.schema.json`; verify displayed summary counts.

A missing browser, unavailable PDF parser, absent search results, deadline, or inconclusive check belongs in coverage. Do not convert it into a website defect. The output must state pages actually collected, timestamps, capabilities used, elapsed time and unfinished stages.

For manual execution, preserve the same coverage and evidence contract. Do not claim an executed diagnostic or performance measurement unless it actually ran. Never predict bounce rates or promise commercial assistant ranking improvements from this public audit.
