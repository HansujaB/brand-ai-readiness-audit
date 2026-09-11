---
name: engagement-audit
description: Audit observed obstacles between a visitor question, the landing-page answer and an appropriate next action. Use for public-page relevance, desktop/mobile visibility and lab performance observations.
license: MIT
metadata:
  compatibility: Requires the intact marketplace and Python with requests, beautifulsoup4 and jsonschema. Playwright and pypdf are optional. Anonymous read-only public HTTP(S) evidence only.
---

Run `python skills/engagement-audit/scripts/engagement_check.py URL --output findings.json --diagnostics-output evidence.json` from the marketplace root. `auditlib/engagement.py` owns engagement reasoning; `auditlib/browser.py` collects instrumented browser evidence. Read [the review checklist](references/checklist.md) and [implementation notes](references/implementation.md).

1. Select page purpose from explicit structured types and URL path. Do not classify a page from the hostname. Unknown purpose stays informational; do not require a sales CTA on every page.
2. Match visitor questions to their relevant public information links. Collect paths before browser work, preserving observations on budget exhaustion. HTTP success alone does not establish an answer. Check destination content and product context; a different product does not answer the original question.
3. Sample desktop and mobile/touch rendering with bounded stability checks, two scroll positions, keyboard focus and local disclosure states. Only explicit same-origin GET search endpoints may be sampled using the public page heading; never submit enquiry, cart or checkout forms. Every network request remains subject to the shared read-only policy. Explain untested workflows rather than claiming they passed.
4. Use visible coherent answer sections. Lexical criteria establish answer candidates, not semantic correctness or applicability to every visitor. Record pass/fail/unknown at the actual scope inspected. Hidden raw content is not a visible answer.
5. Accept a next-step candidate only when visible, enabled and receiving pointer events. Partial or unstable rendering cannot support visual findings or passes. Preserve blockers, locators, bounds and viewport in detailed evidence. Missing/disabled actions with unresolved prerequisites stay unknown.
6. Restrict overflow findings to observed reading obstacles, excluding inherently two-dimensional tables. Report unnamed controls; treat small touch targets as review suggestions because spacing/exceptions matter. Do not recommend citations for every percentage or comparisons for every occurrence of "best".
7. Return compact business findings with evidence and prioritized actions. Keep diagnostic arrays in --diagnostics-output. Merge duplicate controls across viewports; count the displayed findings exactly. No finding quota, bounce prediction or implied site-wide pass.

Performance metrics are short instrumented lab observations with cached anonymous delivery. Observed CLS uses session windows; INP and field percentiles remain unavailable. Mobile emulation, a bounded focus sample and disclosure testing are not complete accessibility or real-device certification.
