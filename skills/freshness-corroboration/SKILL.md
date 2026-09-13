---
name: freshness-corroboration
description: Check fact context, published freshness and consistency between pages of the same website in one country and language. Use for conflicting prices, policies, dates and ambiguous organization statements; no outside-source research.
license: MIT
metadata:
  compatibility: Python with requests, beautifulsoup4 and jsonschema. Optional Chromium/Playwright and pypdf. Keep the whole marketplace together. Public website access only.
allowed-tools: Read Write Bash
---

Within this marketplace, corroboration means comparing the website's own pages. Run `python skills/freshness-corroboration/scripts/entity_check.py URL` for the standalone check; it writes only `<company>_report.json`. Read [the checklist](references/checklist.md) when resolving claims.

1. Identify the site's decision-relevant claims from actual content: prices and commitments, delivery areas/timing, return exceptions, warranty conditions, specifications, service coverage or organization details. Use the page's language and audience. Keep collection and follow-up within the supplied URL's exact origin (scheme, hostname and effective port), including redirects and resources. Do not fetch news, directories, reviews or other publishers.
2. Extract the claim together with its entity, value, units, market, date, variant and exceptions. Separate production, dispatch, delivery, cancellation, returns, refunds and warranty events. Preserve exact source spans and URLs. The runner extracts structured prices and duration candidates; unsupported language or wording still needs review of the published content. Include offering, compatibility, service areas and organization identity rather than focusing only on money and policies.
3. Compare the same claim across relevant website pages, such as a product page and its policy, a pricing page and its offer description, or a help article and the current service page. Resolve regional, historical and product differences first. Identical policy wording with different durations is reportable at its observed scope; different wording or exceptions needs review. Missing product metadata must not prevent reasoning from clear prose evidence.
4. Stress-test whether an isolated answer carries its qualifications. Apply general terms only when their relationship to the offer is established. Different FAQ answers and unrelated promotional phrases containing "only" are not automatically missing context. Preserve explicit single-offer billing conditions; send ambiguous extracted qualifications to review. Check visible About/contact information and structured business identity together, keeping trading and legal names distinct when the site explains them.
5. Check explicit offer expiry and visible/structured modification-date disagreements. Read current on-site policy or service evidence before declaring old prose stale. An expired metadata field is a metadata issue; publication age, copyright years and absent dates alone do not prove staleness. Never suggest refreshing a date without a substantive update.
6. Resolve high-impact uncertainties from the internal evidence using the cited same-locale page within the original deadline. Preserve both source spans internally. The business report needs only a short comparison and targeted correction; do not export the review queue or create another file.

The standalone check uses static website evidence; the full audit can additionally use the crawl/render specialist. Cross-site agreement and historical facts unavailable on the website remain outside this audit's scope.
