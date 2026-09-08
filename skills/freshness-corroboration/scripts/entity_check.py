#!/usr/bin/env python3
"""
entity_check.py — the scriptable half of freshness-corroboration:
Organization/Person schema + sameAs extraction, and staleness-signal
detection (dateModified / "last updated" markers).

The cross-web corroboration search (step 2 in SKILL.md) and the bare
brand-name collision search (step 3) are deliberately NOT done here --
they require a live web-search tool with judgment about which domains
count as "independent," which this script cannot safely automate
without a search API key and without risking naive false positives.
Run those steps using the calling agent's own search tool, following
the false-positive guards documented in SKILL.md, and merge the results
with this script's output.

Usage:
    python entity_check.py https://example.com [--pages url1 url2 ...]
"""
import sys
import json
import argparse
import re

import requests
from bs4 import BeautifulSoup

TIMEOUT = 15
HEADERS = {"User-Agent": "brand-ai-readiness-audit/1.0 (read-only audit bot)"}

TIME_SENSITIVE_HINTS = ("pricing", "plans", "specs", "spec-sheet", "blog", "news", "product")


def fetch(url):
    try:
        return requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None


def extract_jsonld(soup):
    items = []
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(s.string or "{}")
        except Exception:
            continue
        items.extend(data if isinstance(data, list) else [data])
    return [i for i in items if isinstance(i, dict)]


def check_entity_and_staleness(pages):
    findings = []
    for page in pages:
        resp = fetch(page)
        if resp is None or resp.status_code >= 400:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        jsonld = extract_jsonld(soup)

        for item in jsonld:
            if item.get("@type") in ("Organization", "Person"):
                same_as = item.get("sameAs")
                if not same_as:
                    findings.append({
                        "title": f"{item.get('@type')} schema present without sameAs links",
                        "severity": "medium",
                        "evidence": f"{page}: {item.get('@type')} JSON-LD found but 'sameAs' is missing or empty.",
                        "affected_urls": [page],
                        "category": "discoverability",
                        "confidence": "high",
                        "suggested_action": {
                            "summary": "Add sameAs links to Wikidata/Wikipedia/verified social profiles to aid entity disambiguation. Severity should be raised if a name-collision search (run separately) confirms real ambiguity risk.",
                            "priority": "medium",
                        },
                    })

        is_time_sensitive = any(hint in page.lower() for hint in TIME_SENSITIVE_HINTS)
        if is_time_sensitive:
            has_date_meta = any(i.get("dateModified") or i.get("datePublished") for i in jsonld)
            visible_text = soup.get_text(" ", strip=True).lower()
            has_visible_marker = bool(re.search(r"last updated|updated on|revised", visible_text))
            if not has_date_meta and not has_visible_marker:
                findings.append({
                    "title": "Time-sensitive page has no freshness signal",
                    "severity": "medium",
                    "evidence": f"{page}: no dateModified/datePublished in JSON-LD and no visible 'last updated' text found on a page that appears time-sensitive.",
                    "affected_urls": [page],
                    "category": "discoverability",
                    "confidence": "medium",
                    "suggested_action": {
                        "summary": "Add a dateModified field to structured data and/or a visible 'last updated' marker on pricing/spec/blog content.",
                        "priority": "medium",
                    },
                })
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site_url")
    ap.add_argument("--pages", nargs="*", default=[])
    args = ap.parse_args()
    pages = [args.site_url] + args.pages
    findings = check_entity_and_staleness(pages)
    print(json.dumps(findings, indent=2))
    print(
        "\n# NOTE: cross-web corroboration and brand-name-collision search were "
        "NOT run by this script -- perform those with your own web-search tool "
        "per SKILL.md steps 2 and 3, then merge results.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
