---
name: engagement-audit
description: Evaluate whether visitors to one website locale can find an applicable answer and reach a useful public next step on desktop and mobile. Use for content gaps, navigation obstacles and observed control problems.
license: MIT
metadata:
  compatibility: Python with requests, beautifulsoup4 and jsonschema. Optional Chromium/Playwright and pypdf. Keep the whole marketplace together. Public website access only.
allowed-tools: Read Write Bash
---

Run `python skills/engagement-audit/scripts/engagement_check.py URL` for the standalone check; it writes only `<company>_report.json`. Read [the checklist](references/checklist.md) before interpreting a journey.

1. Establish the page purpose from its content, structured types and local path. A regional root is still a homepage; short product paths, returns, delivery and support pages need their own visitor questions. For unfamiliar languages or layouts, verify the inferred purpose against the actual page rather than treating a URL heuristic as authoritative.
2. Ask what the visitor needs to decide: offering/orientation, cost and commitment, suitability, applicable conditions, getting help or the next documentation step. Inspect the specific answer and its qualifications. A long paragraph or scattered keyword matches do not establish an answer. The runner's lexical matches are candidates for this review.
3. Follow relevant anonymous public information links within the supplied URL's exact origin (scheme, hostname and effective port) and selected country/language. Keep browser assets and all redirects within that origin too. Verify the destination's content and subject, not only HTTP success. Keep the product or service context: a policy for another item does not answer the original question. No checkout, cart changes, authentication or enquiry submission. Explicit public GET search on the same origin is allowed; inspect relevance before describing it as successful.
4. Use representative desktop/mobile samples and retain observation-specific reliability. Readability can remain observable when an unrelated image fails. Geometry needs styles/fonts; missing answers and interaction behavior need sufficient scripts/data. Inspect relevant controls for visible labels, enabled state, pointer access, focus and local disclosures. Do not convert a failed optional resource into a blanket rejection of everything on the page.
5. Where a complete relevant sample exposes a covered control, unreadable overflow or unnamed control, record the exact element and correction. Where an expected answer or next step is not found, give a scoped content/navigation improvement or a targeted follow-up question. Consider prerequisites, consent state and below-fold content before calling an action unavailable. Preserve table/reflow and touch-target exceptions.
6. Keep question-by-question analysis, browser measurements and verification evidence internal. In `<company>_report.json`, summarize only the business obstacle, short evidence and action, using the orchestrator's compact contract. Resolve uncertainty within the original deadline. Do not describe a sampled information path as a completed purchase or infer bounce rates from browser timing.
