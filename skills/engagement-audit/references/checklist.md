# Engagement Audit — Detailed Checklist

## 1. Above-fold clarity
- Evidence: the actual H1/hero text and the sentence(s) immediately following it.
- Not a defect: a slogan-first hero paired with an immediate, concrete subheading.

## 2. CTA presence
- Evidence: list of above-fold links/buttons and their labels.
- Not a defect: a purely editorial/content page (e.g. a blog post) is not expected to carry a hard sales CTA — judge against the page's evident purpose.

## 3. Load performance (approximate)
- Evidence: TTFB and total GET time in seconds/ms.
- Not a defect: slower load justified by page complexity/category; this is a floor signal, not lab-grade — pair with the manual fallback before treating it as conclusive.

## 4. Mobile viewport
- Evidence: exact `<meta name="viewport">` content attribute value (or its absence).
- Not a defect: none — this is close to a binary, low-ambiguity check.

## 5. Orientation for returning visitors
- Evidence: whether any personalization/retention markers are observable from a first anonymous fetch.
- Not a defect: brochure/informational sites with no login or repeat-transaction model.

## 6. Help/chat affordance
- Evidence: detected widget script name, or the contact/help link found (or confirmed absent).
- Not a defect: none directly, but severity should scale with how transaction-heavy the site is (an e-commerce checkout flow needs this more than a simple portfolio site).

## 7. Readability
- Evidence: computed readability score; paragraph length distribution; presence/absence of subheadings and bullets.
- Not a defect: low readability score alone on content for an expert audience — only flag when combined with a genuine structural problem (no breaks, no headings).

## Severity quick-reference
| Trigger | Severity |
|---|---|
| No CTA anywhere above the fold on a conversion-intent page | high |
| Missing/broken mobile viewport config | high |
| No help/chat/contact path findable at all | medium |
| Hero has no concrete "what is this" statement | medium |
| Dense unbroken text with no structural breaks | medium |
| Slow approximate load time (needs manual confirmation) | low–medium |
| No visible returning-visitor personalization | low (informational) |
