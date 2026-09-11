# Engagement implementation and verification

## Review closure

The 23 review items were addressed through replacement of the engagement engine, browser observation changes, execution ordering, compact output and regression coverage. The bounded implementation remains an evidence sampler, not a semantic or accessibility certification system.

| Review items | Implementation |
| --- | --- |
| 1 budget starvation | Static path checks precede browser work. Final engagement processing occurs even after a budget exception. Per-viewport browser allowance preserves collected work. |
| 2, 8, 9 answer assessment | Question-specific lexical criteria must co-occur in visible sections. Candidate passes include their precise scope; unsupported answers remain unknown. |
| 3 classification | page_purpose uses explicit types and path, not hostnames; adds service/homepage/documentation/article purposes. |
| 4, 5, 7 action mistakes | Enabled state, invisible ancestors, inert state, accessible labels, task-specific action patterns and common cart labels. Unknown languages/actions are not automatic defects. |
| 6 partial rendering | Unstable/blocked/failed/frame-incomplete samples cannot create visual passes or defects. |
| 10, 11 destination checks | Match links to each question, inspect destination content, reject soft-error candidates. HTTP 200 is not answer success. |
| 12 context | Record original product and detect different named product destinations. Ambiguous general policies remain unverified; personalized context is not fabricated. |
| 13 readiness | Repeated text/action-geometry stability observations replace the single 750 ms delay. A later change outside the sample can still be missed. |
| 14 mobile | Mobile/touch/device-scale configuration and explicit viewport-width measurement. |
| 15 sampling | Remove first-100 action truncation; include partial intersections, scroll samples and open shadow controls. |
| 16, 20 evidence | Identify overflow text/control/blocker with locator and rectangle. Tables are excluded from blanket overflow defects. Repeated viewport issues merge by element. |
| 17 reconstructed browser | Preserve redirects via browser-visible redirects. Anonymous/cached transport is still disclosed; unavailable resources suppress conclusions. Cookies and non-GET requests remain blocked. |
| 18 performance | Correct observed CLS session-window aggregation; retain instrumentation disclosure and unavailable INP/field data. |
| 19 recommendations | Delete generic percentage, superlative and absent-table heuristics. Small-target suggestions require measured evidence and exception review. |
| 21 output ordering | Deduplicate suggestions and rank before output limits; merge repeated control issues. |
| 22 JSON | Engagement and combined CLI emit the small owner schema; optional diagnostics preserve evidence arrays. |
| 23 tests | New paired engagement regressions plus retained collection/browser/supervisor/freshness safety checks. Retire old extractor benchmark and generated reports. |

## Research

- [Playwright actionability](https://playwright.dev/docs/actionability): enabled, stable and receiving-event checks are distinct. This audit additionally excludes full transparency because perceptibility matters.
- [Playwright emulation](https://playwright.dev/docs/emulation): mobile and touch configuration differ from resizing a viewport.
- [W3C reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html): two-dimensional content has relevant exceptions; document overflow alone is insufficient.
- [W3C target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html): spacing and exceptions matter, so small targets generate review suggestions rather than automatic violations.
- [CLS](https://web.dev/articles/cls): aggregate layout shifts in session windows; short instrumented observations are not field measurements.

## Deliberate limits

No arbitrary user journey can be proven by keyword tests. Supplied page content supports bounded answer candidates only. Non-GET forms, purchasing, authentication, all-language semantic evaluation, all frames, all keyboard paths and real-user performance are not claimed. These limits appear in coverage/checks rather than being hidden behind a clean report.

Run tests from the marketplace root with `.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -v`. Browser regressions require Playwright and Chromium. Fresh live smoke results should be stored in a temporary directory, not committed as regression fixtures.


## Validation on 2026-09-11

- Full regression run: 80 tests passed in 52.6 seconds, including actual Chromium, redirect semantics, native/menu disclosure states and owned-worker shutdown.
- Final focused engagement run after preserving the zoom-declaration check: 25 tests passed.
- Engagement and orchestrator skill frontmatter validated.
- Littlebox standard smoke: 5 HTML pages, 7 visitor questions, 77 requests, 48.6 seconds; collection/engagement/render stages recorded and no internal audit error. Browser observations were incomplete, with zero confirmed findings. This does not establish that the site has no engagement issues. The run's disclosure timeout prompted per-control exception handling; an incomplete disclosure no longer discards the whole page sample.
- Removed 13 obsolete benchmark/report/fixture files, the retired engagement implementation, the unused price extractor and its obsolete tests. Retained useful safety/browser/freshness tests and replaced lost scope/ownership checks with identified-product regressions. Generated reports are not kept in the test tree.
