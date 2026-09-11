# Brand AI readiness audit

Four skills diagnose machine access, lost fact context, conflicting claims and observed visitor-journey obstacles. The Python runner shares one robots-enforcing evidence collector and emits a validated JSON report. It never modifies the audited site.

| Skill | Responsibility |
|---|---|
| audit-orchestrator | Shared evidence, coverage, deadlines, deduplication, prioritization and schema validation |
| crawl-render-audit | Access, indexability, raw/rendered facts, media and markup consistency |
| freshness-corroboration | Fact extraction stress tests, scoped claims, identity and external evidence |
| engagement-audit | Visitor questions, visible actions, mobile obstacles and performance observations |

## Run

Keep the whole marketplace together: standalone entrypoints import the root auditlib package.

```sh
python -m pip install -r requirements.txt
python skills/audit-orchestrator/scripts/run_audit.py https://example.com --brand "Example" --depth standard --output report.json
```

Optional browser/PDF capabilities:

```sh
python -m pip install -r requirements-optional.txt
python -m playwright install chromium
```

Use `--no-browser` to disable rendering. Use `--facts-file facts.json` for 3–5 question/terms/context records and `--search-results sources.json` for a researcher-grouped external sample. See [the input and report contract](skills/audit-orchestrator/references/schema.md). Every command emits a compact owner report; --diagnostics-output retains detailed evidence separately.

Quick/standard/deep sample up to 1/5/9 pages under one 270-second work budget. The supervisor enforces a whole-process deadline and preserves partial reports. `--budget 30` is useful for bounded smoke checks. A deeper sample does not remove the time limit. No five-minute performance guarantee is assumed without measurement.

## Evidence and limitations

Owner findings contain ID, title, severity, evidence and suggested action, with a small coverage statement. Detailed evidence, verification steps, request logs, confidence and journey checks are in the optional diagnostics report. See skills/engagement-audit/references/implementation.md for the engagement review changes.

Training opt-outs do not become search defects. Missing schema, missing dates, absent sameAs, absent browser/search and a small site without a sitemap do not automatically produce findings. Raw/rendered checks compare substantive facts, not text length. Claim comparisons separate contradictions, historical differences, regional differences and insufficient scope.

Fact tests preserve headings/table headers and test supplied context. Automatic candidates currently focus on prices and return windows; other facts need explicit questions. Extractive drafts preserve source spans; this is not an independent answer-quality evaluation. External source imports support capped corroboration, ownership and syndicated-group deduplication; live search is performed by the calling agent, not silently claimed by the runner. Unknown ownership never establishes independence.

Browser observations inspect desktop/mobile actions, accessible names and obstruction without clicks or form submission. English/Hindi candidate labels are supported; broader language semantics need review. Public navigation candidates do not prove a complete conversion journey. Returning-user personalization is unobserved. HTTP timing, instrumented browser lab metrics and real-user field metrics are separate. No actual bounce rate, commercial assistant ranking gain or complete semantic correctness is inferred.

The network layer checks public addresses and redirects, disables environment credentials/proxies and cookies, and blocks transactional paths/non-GET browser traffic. Connections are pinned to validated public IP addresses while retaining TLS hostname verification. Redirected browser subresources that cannot be safely replayed are aborted and reported as partial coverage. The auditable request log supports prohibited-request checks.

## Validate

```sh
python -m unittest discover -s tests -v
```

Browser regression tests require Playwright and Chromium. Paired fixtures do not establish real-world generalization; use separate temporary live smoke reports. The obsolete extractor benchmark and generated reports were removed.

Download limits are configurable: `--max-response-mb 20 --max-download-mb 100` sets the default decimal-MB allowances for decoded response bodies. All HTTP/browser requests share the total budget and deadline; cache hits count once. Oversized responses are reported as incomplete coverage with observed byte counts, never site defects. Dependent stages are not_run when no complete page was collected.
