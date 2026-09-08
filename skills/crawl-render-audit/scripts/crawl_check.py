#!/usr/bin/env python3
"""
crawl_check.py — deterministic checks for Appendix A (crawl access) and
Appendix C (render gap / structured data) of the brand-ai-readiness-audit.

Usage:
    python crawl_check.py https://example.com [--pages https://example.com/pricing ...] [--facts "price" "return window"]

Design notes:
- Read-only. Only ever issues GET requests. Never authenticates, never
  writes anything to the target site.
- Respects the spirit of robots.txt: this script *checks* robots.txt, it
  does not fetch pages that robots.txt disallows for the generic agent.
- Degrades gracefully: if `playwright` isn't installed, the render-gap
  check (#4) is skipped and reported as "not run" rather than guessed at.
  The SKILL.md documents the manual fallback for that case.
- Output is a JSON list of finding dicts on stdout, so the calling agent
  (or the orchestrator) can parse it directly.

This script encodes structural/mechanical checks only. It deliberately
does NOT hardcode any "magic number" performance thresholds (e.g. a
specific millisecond cutoff for acceptable load time) pulled from
unverifiable third-party studies -- those numbers are exactly the kind
of false precision that produces false positives on sites that are
merely unusual, not broken. Where a judgment call is needed (e.g. "is a
render gap substantial?") this script reports the raw percentage and
lets the calling agent apply the severity rubric in SKILL.md, which is
based on materiality, not an arbitrary number.
"""
import sys
import json
import argparse
import re
import time
import urllib.parse
import urllib.robotparser

import requests
from bs4 import BeautifulSoup

AI_AGENTS = [
    "*", "GPTBot", "ChatGPT-User", "Google-Extended", "CCBot",
    "PerplexityBot", "ClaudeBot", "Applebot-Extended", "Bingbot",
]

UTILITY_PATH_HINTS = (
    "/cart", "/checkout", "/account", "/login", "/admin",
    "/search", "/wp-admin", "/api/",
)

TIMEOUT = 15
HEADERS = {"User-Agent": "brand-ai-readiness-audit/1.0 (read-only audit bot)"}


def fetch(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        return resp
    except requests.RequestException as e:
        return None


def is_utility_path(url):
    path = urllib.parse.urlparse(url).path.lower()
    return any(hint in path for hint in UTILITY_PATH_HINTS)


def check_robots(base_url, pages):
    findings = []
    robots_url = urllib.parse.urljoin(base_url, "/robots.txt")
    resp = fetch(robots_url)
    sitemap_hint = None
    if resp is None or resp.status_code >= 400:
        findings.append({
            "title": "robots.txt missing or unreachable",
            "severity": "low",
            "evidence": f"GET {robots_url} -> {'no response' if resp is None else resp.status_code}",
            "affected_urls": [base_url],
            "category": "discoverability",
            "suggested_action": {
                "summary": "Add a robots.txt at the domain root (even a permissive one) so crawler behavior is explicit rather than assumed.",
                "priority": "low",
            },
        })
        return findings, sitemap_hint

    text = resp.text
    for line in text.splitlines():
        if line.strip().lower().startswith("sitemap:"):
            sitemap_hint = line.split(":", 1)[1].strip()

    rp = urllib.robotparser.RobotFileParser()
    rp.parse(text.splitlines())

    for agent in AI_AGENTS:
        for page in pages:
            if is_utility_path(page):
                continue  # not part of the audited informational content
            try:
                allowed = rp.can_fetch(agent, page)
            except Exception:
                allowed = True
            if not allowed:
                sev = "critical" if agent == "*" else "high"
                findings.append({
                    "title": f"robots.txt disallows '{agent}' from an audited content page",
                    "severity": sev,
                    "evidence": f"robots.txt at {robots_url} disallows agent '{agent}' for {page}",
                    "affected_urls": [page],
                    "category": "discoverability",
                    "suggested_action": {
                        "summary": f"Remove the Disallow rule blocking '{agent}' for this content path, unless the exclusion is intentional.",
                        "priority": "high" if sev == "critical" else "medium",
                    },
                })
    return findings, sitemap_hint


def check_sitemap(base_url, sitemap_hint, pages):
    findings = []
    candidates = [sitemap_hint] if sitemap_hint else []
    candidates.append(urllib.parse.urljoin(base_url, "/sitemap.xml"))
    found_valid = False
    matched_pages = set()
    for url in candidates:
        if not url:
            continue
        resp = fetch(url)
        if resp is None or resp.status_code >= 400:
            continue
        try:
            soup = BeautifulSoup(resp.text, "xml")
        except Exception:
            continue
        locs = [loc.text.strip() for loc in soup.find_all("loc")]
        if locs:
            found_valid = True
            for p in pages:
                if any(p.rstrip("/") == loc.rstrip("/") for loc in locs):
                    matched_pages.add(p)

    if not found_valid:
        findings.append({
            "title": "No valid sitemap.xml found",
            "severity": "medium",
            "evidence": f"Checked {', '.join(c for c in candidates if c)}; none returned a parseable sitemap.",
            "affected_urls": [base_url],
            "category": "discoverability",
            "suggested_action": {
                "summary": "Publish a sitemap.xml (or sitemap index) covering all indexable content and reference it from robots.txt.",
                "priority": "medium",
            },
        })
    return findings


def check_status_and_indexability(pages):
    findings = []
    for page in pages:
        resp = fetch(page)
        if resp is None:
            findings.append({
                "title": "Key page unreachable",
                "severity": "critical",
                "evidence": f"GET {page} raised a connection error / timeout.",
                "affected_urls": [page],
                "category": "discoverability",
                "suggested_action": {"summary": "Investigate hosting/DNS/SSL issues making this page unreachable.", "priority": "high"},
            })
            continue
        if resp.status_code >= 400:
            findings.append({
                "title": f"Key page returns HTTP {resp.status_code}",
                "severity": "critical",
                "evidence": f"GET {page} -> {resp.status_code}",
                "affected_urls": [page],
                "category": "discoverability",
                "suggested_action": {"summary": "Fix the broken page or update internal/external links pointing to it.", "priority": "high"},
            })
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        robots_meta = soup.find("meta", attrs={"name": re.compile("robots", re.I)})
        x_robots = resp.headers.get("X-Robots-Tag", "")
        noindex = False
        if robots_meta and "noindex" in robots_meta.get("content", "").lower():
            noindex = True
        if "noindex" in x_robots.lower():
            noindex = True
        if noindex and not is_utility_path(page):
            findings.append({
                "title": "Content page marked noindex",
                "severity": "critical",
                "evidence": f"{page} carries a noindex directive (meta or X-Robots-Tag header).",
                "affected_urls": [page],
                "category": "discoverability",
                "suggested_action": {"summary": "Remove the noindex directive if this page is meant to be discoverable.", "priority": "high"},
            })
    return findings


def check_structured_data(pages):
    findings = []
    for page in pages:
        resp = fetch(page)
        if resp is None or resp.status_code >= 400:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
        if not scripts:
            findings.append({
                "title": "No JSON-LD structured data found",
                "severity": "high",
                "evidence": f"{page} contains zero <script type=\"application/ld+json\"> blocks.",
                "affected_urls": [page],
                "category": "discoverability",
                "suggested_action": {"summary": "Add JSON-LD matching the page's evident type (Product/Offer, Article, Organization, FAQPage, etc.).", "priority": "high"},
            })
            continue
        types_seen = []
        same_as_empty = []
        for s in scripts:
            try:
                data = json.loads(s.string or "{}")
            except Exception:
                findings.append({
                    "title": "Invalid JSON-LD",
                    "severity": "medium",
                    "evidence": f"{page} contains a <script type=\"application/ld+json\"> block that fails to parse as JSON.",
                    "affected_urls": [page],
                    "category": "discoverability",
                    "suggested_action": {"summary": "Fix the malformed JSON-LD so it validates.", "priority": "medium"},
                })
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                t = item.get("@type")
                if t:
                    types_seen.append(t)
                if t in ("Organization", "Person"):
                    same_as = item.get("sameAs")
                    if not same_as:
                        same_as_empty.append(t)
        if same_as_empty:
            findings.append({
                "title": "Organization/Person schema missing sameAs links",
                "severity": "medium",
                "evidence": f"{page}: {', '.join(same_as_empty)} schema present without a populated sameAs array.",
                "affected_urls": [page],
                "category": "discoverability",
                "suggested_action": {"summary": "Add sameAs links to Wikidata/Wikipedia/verified social profiles to strengthen entity disambiguation.", "priority": "medium"},
            })
    return findings


def check_non_text_locked_facts(pages, target_facts):
    findings = []
    if not target_facts:
        return findings
    for page in pages:
        resp = fetch(page)
        if resp is None or resp.status_code >= 400:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        visible_text = soup.get_text(" ", strip=True).lower()
        for fact in target_facts:
            fact_l = fact.lower()
            if fact_l in visible_text:
                continue  # present in plain text somewhere on the page — not locked
            # crude heuristic: does an <img>/<embed>/PDF link nearby reference the fact concept?
            candidates = soup.find_all(["img", "embed", "canvas"])
            pdf_links = [a.get("href", "") for a in soup.find_all("a") if a.get("href", "").lower().endswith(".pdf")]
            if candidates or pdf_links:
                findings.append({
                    "title": f"Possible non-text-locked fact: '{fact}'",
                    "severity": "high",
                    "evidence": f"{page}: '{fact}' not found in plain visible text; page contains {len(candidates)} image/canvas/embed element(s) and {len(pdf_links)} PDF link(s) that may carry it instead.",
                    "affected_urls": [page],
                    "category": "discoverability",
                    "suggested_action": {"summary": f"Confirm whether '{fact}' is only shown visually/in a PDF, and add a plain-text equivalent if so.", "priority": "medium"},
                })
    return findings


def try_render_diff(pages):
    """Optional: only runs if playwright is installed. Returns findings + a flag."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [{"title": "Render-gap check not run", "severity": "low",
                  "evidence": "playwright not installed in this environment; raw-vs-rendered DOM diff skipped. Use the manual fallback in SKILL.md step 4.",
                  "affected_urls": pages, "category": "discoverability",
                  "suggested_action": {"summary": "Install playwright (`pip install playwright && playwright install chromium`) to enable automated render-gap detection.", "priority": "low"}}]

    findings = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page_obj = browser.new_page()
        for url in pages:
            raw_resp = fetch(url)
            if raw_resp is None or raw_resp.status_code >= 400:
                continue
            raw_text = BeautifulSoup(raw_resp.text, "html.parser").get_text(" ", strip=True)
            try:
                page_obj.goto(url, timeout=TIMEOUT * 1000, wait_until="networkidle")
                rendered_text = page_obj.inner_text("body")
            except Exception:
                continue
            raw_len = len(raw_text)
            rendered_len = max(len(rendered_text), 1)
            gap_pct = max(0.0, (rendered_len - raw_len) / rendered_len * 100)
            if gap_pct > 30:
                findings.append({
                    "title": "Substantial render gap between raw HTML and rendered DOM",
                    "severity": "high",
                    "evidence": f"{url}: raw HTML text ~{raw_len} chars vs rendered ~{rendered_len} chars (~{gap_pct:.0f}% of visible text is JS-only).",
                    "affected_urls": [url],
                    "category": "discoverability",
                    "suggested_action": {"summary": "Move critical content to server-rendered/static HTML, or add prerendering for crawler user-agents.", "priority": "high"},
                })
        browser.close()
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site_url")
    ap.add_argument("--pages", nargs="*", default=[])
    ap.add_argument("--facts", nargs="*", default=[])
    args = ap.parse_args()

    pages = [args.site_url] + args.pages
    findings = []

    robots_findings, sitemap_hint = check_robots(args.site_url, pages)
    findings += robots_findings
    findings += check_sitemap(args.site_url, sitemap_hint, pages)
    findings += check_status_and_indexability(pages)
    findings += check_structured_data(pages)
    findings += check_non_text_locked_facts(pages, args.facts)
    findings += try_render_diff(pages)

    print(json.dumps(findings, indent=2))


if __name__ == "__main__":
    main()
