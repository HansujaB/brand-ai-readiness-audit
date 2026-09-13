# Research and implementation boundaries

The competition brief motivates evidence-backed discoverability and engagement checks. This version follows the requested website-only scope; it does not evaluate outside-source agreement or actual commercial assistant citations.

| Area | Primary reference | Applied decision |
|---|---|---|
| Crawler access | [Robots Exclusion Protocol](https://www.rfc-editor.org/rfc/rfc9309.html) | Respect matched rules and distinguish unavailable permission from a website defect. |
| Index/snippet controls | [Google robots directives](https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag) | Preserve scope and exact directives; avoid conflating training controls with search availability. |
| Discovery | [Google sitemap guidance](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap) | Use sitemaps as supplementary discovery. Locale filtering and the separate download allowance are engineering decisions. |
| Offers and variants | [Google product snippets](https://developers.google.com/search/docs/appearance/structured-data/product-snippet), [product variants](https://developers.google.com/search/docs/appearance/structured-data/product-variants) | Compare identified products with their currency, variant and conditions; do not infer a brand-wide price. |
| Dates | [Google publication dates](https://developers.google.com/search/docs/appearance/publication-dates) | Distinguish publication and modification dates; no fabricated freshness updates. |
| Browser collection | [Playwright CDP sessions](https://playwright.dev/python/docs/api/class-cdpsession), [Chromium Fetch protocol](https://chromedevtools.github.io/devtools-protocol/tot/Fetch/) | Intercept at the Chromium request stage and deliver each checked redirect. Keep direct browser networking offline so unattached targets cannot bypass the collector. |
| Visible controls | [Playwright actionability](https://playwright.dev/python/docs/actionability) | Preserve visible/enabled state, geometry and blockers. Positive observations and absence claims have different resource needs. |
| Reflow and touch | [WCAG reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html), [target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) | Record concrete obstacles and respect exceptions; no accessibility certification claim. |
| Lab observations | [Cumulative Layout Shift](https://web.dev/articles/cls) | Keep instrumented observations distinct from real-user metrics; no bounce prediction. |
| Fact context | [Contextual retrieval](https://www.anthropic.com/engineering/contextual-retrieval) | Preserve headings and applicable qualifications. Local extractive drafts do not reproduce or establish that research's results. |
| Public network boundary | [OWASP SSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) | Public-IP validation, connection pinning and repeated redirect checks remain in force. |

The requested network boundary is the supplied URL's exact origin (scheme, hostname and effective port), including assets, robots.txt and redirects. It excludes other hosts before address validation, with no CDN exception. This scope comes from the user request. Request counts, page caps, locale tie-breakers, matching heuristics and severity levels are engineering choices. Tests pair positive and negative examples for scope, context and policy comparisons; they do not establish real-world generalization or universal semantic correctness. The skill procedures provide bounded source-grounded review for the important questions the automatic checks cannot resolve.
