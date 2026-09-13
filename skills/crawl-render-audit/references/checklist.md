# Access and representation evidence

| Check | Evidence needed | Decision and follow-up |
|---|---|---|
| Access | URL, exact robots group/rule, status or index directive | Describe the affected crawler and scope; preserve intentional training policy. |
| Discovery | Selected locale, representative products/services and normal links | Sample distinct offerings before pagination; check cached failures and bounded important-link targets. Filter locale before downloading sitemap children. |
| Search titles | Actual title text and distinct page subjects | Report empty/conflicting titles and duplicates across different canonical pages; do not enforce arbitrary character counts. |
| Search descriptions | Published description and page content | Missing or duplicated descriptions are scoped improvements, not proof of lost rankings. |
| Canonicals | Declaration and observed target response/directives | Report missing targets or noindex destinations; review semantic relevance. Chains are an improvement. Do not fetch out-of-origin destinations. |
| Language alternatives | Published hreflang values and destinations | Conflicting destinations for one language are reportable. Absence on a single-language site is not a defect; do not crawl other locales. |
| Missing raw fact | Explicit question plus raw span search and observed rendered fact | Compare entity, units and qualifications. Use content reliability for positive observations; do not use incomplete rendering to establish absence. |
| Visual problem | Stable element bounds, styles, viewport and blocker | An unrelated image failure does not invalidate the observation; failed relevant styles/fonts do. |
| Product markup | Sampled product pages, all recognized formats and observed rendered metadata | Count missing Product entities even if another schema type exists. Malformed or unsupported representations need repair/review before claiming complete absence. |
| Product fields | Name and an offers/review/aggregateRating route; applicable offer price | Resolve local references, nested prices and aggregate offers. Validate against the intended search feature; currency/image merchant enhancements are separate from basic snippet requirements. Optional fields do not become mandatory defects. |
| Article/organization data | Actual article or published business identity | Give concrete markup improvements tied to visible facts. Never invent authors, dates, ratings or organizational relationships. |
| Text and images | Semantic headings, image-link names and alternatives | Report observed unnamed image links; review informative versus decorative images. Missing headings or alt attributes alone do not prove all content is inaccessible. |
| Media barrier | Named important fact, extraction result and visual evidence | Unavailable OCR/parser is a tool limitation; provide the next inspection step. |

Use request logs and browser evidence to distinguish site responses, blocked actions, origin/locale exclusions, resource failures and budget exhaustion. The browser has no direct network access. Every collector-delivered resource, robots request and redirect stays on the supplied URL's exact origin and remains public-address validated and robots checked. Other hosts are excluded without a network request; do not infer that omitted dependencies were unnecessary. This makes lab timings instrumented observations.

Review SEO/GEO evidence before spending the entire follow-up allowance on policies. Raw HTML omissions must be described at that representation's scope; observed injected markup can resolve them. Crawler access, readable facts and internal paths support discoverability, but an anonymous site audit cannot establish actual rankings or assistant citation share. Missing Product markup normally has medium priority; high priority needs a material demonstrated barrier, not merely the absence of an optional enhancement.
