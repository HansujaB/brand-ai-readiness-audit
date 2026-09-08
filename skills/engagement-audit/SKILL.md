---
name: engagement-audit
description: Audits why a visitor who successfully arrives at a website would bounce — missing above-the-fold clarity (no headline/subhead answering "what is this and why should I care"), no visible next action or CTA, slow load/time-to-first-byte, incorrect or missing mobile viewport configuration, no orientation cues for returning visitors, no help/chat affordance, and dense unscannable text blocks. Use this skill whenever diagnosing on-site conversion or engagement problems, as distinct from AI-discoverability problems. Called by audit-orchestrator as part of a full AI-readiness audit; can also be used standalone for a quick bounce-risk / landing-page audit.
license: MIT
compatibility: Requires read-only GET access to the target page(s). The load-time measurement here is an approximation (server response + basic asset timing via a plain HTTP client), not a lab-grade Core Web Vitals measurement — the SKILL.md is explicit about that limitation and offers a manual fallback (browser dev tools / PageSpeed Insights) for a precise reading.
allowed-tools: web-fetch, bash/python-execution
metadata:
  category: engagement
  covers-appendix: "engagement synthesis (not in appendix A-F; see Round 2 findings)"
---

# Engagement Audit

## When to use

Use this on the pages a real visitor actually lands on — typically the homepage and 1-2 likely landing pages (a top product/category page, a campaign landing page if one exists). This skill answers a different question from the other two: assume the visitor is already here (crawlability and citation are irrelevant at this point) — what makes them leave in the first few seconds, and what would make them act, return, or trust the site?

Do not use this for crawler-facing structural issues (`crawl-render-audit`) or off-site trust/corroboration (`freshness-corroboration`).

## Procedure

Run `scripts/engagement_check.py <url>` for the scriptable checks (1, 3, 4, 6, 7 below). Checks 2 and 5 need visual/behavioral judgment and are best done by reading the fetched page structure directly (the script surfaces the raw ingredients — heading structure, button/link text — for you to judge).

1. **Above-the-fold clarity.** Identify the first substantial heading (`h1`, or the largest/first prominent text block) and the text immediately following it. Judge: within roughly one screen's worth of content, does it plainly state what the site/product is and why the visitor should care — in plain language, not just a brand slogan or logo?
   - Finding trigger: the hero area is pure brand voice/tagline with no concrete statement of what the thing is or does.
   - **False-positive guard:** a slogan-first hero is not automatically wrong if a clear, concrete subheading follows immediately below it — check the *combination*, not the H1 in isolation.

2. **Next action / CTA presence.** Look for at least one clear, actionable link or button above the fold (and check that every major hero/section has some path forward) — "Get started," "Contact us," "See pricing," "Add to cart," rather than only passive nav links.
   - Finding trigger: no actionable CTA anywhere above the fold, or a CTA that is present but ambiguous (e.g. labeled only "Learn more" with no context of what happens next, repeated as the only CTA everywhere).

3. **Load performance (approximate).** Measure time-to-first-byte and total transfer time for a plain GET of the page (this script does NOT execute JS or measure paint timing — it's a floor-level signal, not a substitute for real user metrics).
   - Finding trigger: TTFB or total fetch time is high enough to plausibly cause abandonment — judge this relative to page complexity and what's typical for the site's category, not against an arbitrary universal millisecond cutoff (a rich data-visualization dashboard has different reasonable load characteristics than a static marketing page).
   - **Manual fallback for a precise reading:** use browser dev tools' Network/Performance tab, or a public tool like PageSpeed Insights, for real FCP/LCP numbers instead of relying solely on this approximation.

4. **Mobile viewport correctness.** Check for `<meta name="viewport" content="width=device-width, initial-scale=1">` (or an equivalent that doesn't disable zoom or fix an absolute width).
   - Finding trigger: viewport meta tag missing, or configured to disable pinch-zoom / fix a non-responsive width.

5. **Orientation for returning visitors.** Look for evidence of context retention — a "Welcome back," recently-viewed items, saved cart, or personalization based on prior visits. This is inherently limited to what's observable without actually being a returning/logged-in user, so treat this as a lower-confidence, informational check rather than a hard pass/fail.
   - Finding trigger: an account-driven or e-commerce site with clearly no visible personalization/retention mechanism at all is worth flagging (as `low`/informational); a first-time-visitor-only site (e.g. a simple brochure site) has nothing to retain and should not be flagged.

6. **Help/chat affordance.** Check for a live-chat widget script (common providers: Intercom, Drift, Zendesk, LiveChat, Crisp, HubSpot), or, absent that, a clearly visible contact/help link/phone number.
   - Finding trigger: no chat widget AND no easily-findable contact/help path from the landing page.

7. **Readability of dense text.** Run a standard readability score (e.g. Flesch Reading Ease) on the main body text, and separately check whether long text blocks are broken up with subheadings, bullets, or short paragraphs.
   - Finding trigger: very low readability score combined with long unbroken paragraphs and no subheadings — flag the combination, not either signal alone (some very technical/expert audiences legitimately need denser prose; the structural signal — no headings/bullets/breaks at all — is the more reliable defect).

## Output

Return a list of finding objects: `{title, severity, evidence, affected_urls, category: "engagement", confidence, suggested_action: {summary, priority}}`. Mark checks 3 and 5 with lower `confidence` given their inherent measurement/observability limits, so the orchestrator and the end reader can weight them appropriately. See `references/checklist.md` for severity guidance.
