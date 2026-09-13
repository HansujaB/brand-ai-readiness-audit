# Access and representation evidence

| Check | Evidence needed | Decision and follow-up |
|---|---|---|
| Access | URL, exact robots group/rule, status or index directive | Describe the affected crawler and scope; preserve intentional training policy. |
| Discovery | Selected country/language and relevant normal links | Filter locale before downloading children. Skip costly supplementary maps once representative pages exist. |
| Missing raw fact | Explicit question plus raw span search and observed rendered fact | Compare entity, units and qualifications. Use content reliability for positive observations; do not use incomplete rendering to establish absence. |
| Visual problem | Stable element bounds, styles, viewport and blocker | An unrelated image failure does not invalidate the observation; failed relevant styles/fonts do. |
| Markup | Identified entity and both visible and structured values | Confirm variant and offer scope. Suggest applicable markup only with a concrete visible fact and purpose. |
| Media barrier | Named important fact, extraction result and visual evidence | Unavailable OCR/parser is a tool limitation; provide the next inspection step. |

Use request logs and browser evidence to distinguish site responses, blocked actions, origin/locale exclusions, resource failures and budget exhaustion. The browser has no direct network access. Every collector-delivered resource, robots request and redirect stays on the supplied URL's exact origin and remains public-address validated and robots checked. Other hosts are excluded without a network request; do not infer that omitted dependencies were unnecessary. This makes lab timings instrumented observations.
