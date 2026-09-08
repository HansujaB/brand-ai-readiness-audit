#!/usr/bin/env python3
"""
run_audit.py — reference composition of the three sub-skills into one
final audit report matching references/schema.md.

This is a convenience for when Python execution + the sibling skill
folders are available on disk (i.e. this marketplace is unzipped
intact). If a calling agent doesn't have subprocess/filesystem access
to the sibling scripts, follow the SKILL.md procedures manually
instead -- the composition logic here (discovery, merge, ordering,
summary) is what matters, not the subprocess mechanism.

Usage:
    python run_audit.py https://example.com [--brand "Example Inc"] [--depth quick|standard|deep]
"""
import sys
import os
import re
import json
import argparse
import subprocess
import datetime
import urllib.parse

import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
CRAWL_SCRIPT = os.path.join(HERE, "..", "..", "crawl-render-audit", "scripts", "crawl_check.py")
ENTITY_SCRIPT = os.path.join(HERE, "..", "..", "freshness-corroboration", "scripts", "entity_check.py")
ENGAGEMENT_SCRIPT = os.path.join(HERE, "..", "..", "engagement-audit", "scripts", "engagement_check.py")

HEADERS = {"User-Agent": "brand-ai-readiness-audit/1.0 (read-only audit bot)"}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
EFFORT_ORDER = {"low": 0, "medium": 1, "high": 2, None: 1}


def discover_key_pages(site_url, max_pages=4):
    """Best-effort discovery of a small representative page sample."""
    pages = []
    try:
        resp = requests.get(site_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return pages

    link_hints = {
        "pricing": re.compile(r"pricing|plans", re.I),
        "product": re.compile(r"product|shop|features", re.I),
        "blog": re.compile(r"blog|news|articles", re.I),
        "about": re.compile(r"about|contact", re.I),
    }
    seen = set()
    base = site_url.rstrip("/")
    for label, pattern in link_hints.items():
        if len(pages) >= max_pages:
            break
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if pattern.search(href) or pattern.search(text):
                full = urllib.parse.urljoin(base, href)
                if full.startswith(base) and full not in seen:
                    pages.append(full)
                    seen.add(full)
                    break
    return pages[:max_pages]


def run_script(path, args):
    try:
        result = subprocess.run(
            [sys.executable, path] + args,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return [], f"script {os.path.basename(path)} exited {result.returncode}: {result.stderr[:300]}"
        return json.loads(result.stdout), None
    except Exception as e:
        return [], f"failed to run {os.path.basename(path)}: {e}"


def merge_findings(all_findings):
    """De-duplicate near-identical findings (same title + overlapping affected_urls)."""
    merged = []
    seen_keys = set()
    for f in all_findings:
        key = (f.get("title", "").lower(), tuple(sorted(f.get("affected_urls", []))))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append(f)
    merged.sort(key=lambda f: (
        SEVERITY_ORDER.get(f.get("severity", "low"), 3),
        EFFORT_ORDER.get((f.get("suggested_action") or {}).get("effort"), 1),
    ))
    for i, f in enumerate(merged, start=1):
        f["id"] = f"F-{i:03d}"
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site_url")
    ap.add_argument("--brand", default=None)
    ap.add_argument("--depth", choices=["quick", "standard", "deep"], default="standard")
    args = ap.parse_args()

    max_pages = {"quick": 0, "standard": 4, "deep": 8}[args.depth]
    key_pages = discover_key_pages(args.site_url, max_pages=max_pages) if max_pages else []
    all_pages = [args.site_url] + key_pages

    warnings = []
    findings = []

    crawl_findings, err = run_script(CRAWL_SCRIPT, [args.site_url, "--pages"] + key_pages)
    findings += crawl_findings
    if err:
        warnings.append(err)

    if args.depth != "quick":
        entity_findings, err = run_script(ENTITY_SCRIPT, [args.site_url, "--pages"] + key_pages)
        findings += entity_findings
        if err:
            warnings.append(err)
    else:
        warnings.append("quick depth: freshness-corroboration entity/staleness checks skipped")

    for page in [args.site_url] + key_pages[:2]:
        eng_findings, err = run_script(ENGAGEMENT_SCRIPT, [page])
        findings += eng_findings
        if err:
            warnings.append(err)

    merged = merge_findings(findings)
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in merged:
        sev = f.get("severity", "low")
        if sev in counts:
            counts[sev] += 1

    report = {
        "site": args.site_url,
        "audited_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_metadata": {
            "depth": args.depth,
            "pages_audited": all_pages,
            "capabilities_available": {
                "headless_browser": False,  # set True if playwright import succeeds in crawl_check.py's environment
                "web_search": False,        # entity_check.py does not itself search; corroboration search is a manual/agent step
                "python_execution": True,
            },
            "warnings": warnings,
        },
        "summary": {
            "total_findings": len(merged),
            "critical": counts["critical"],
            "high": counts["high"],
            "medium": counts["medium"],
            "low": counts["low"],
        },
        "findings": merged,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
