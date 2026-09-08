#!/usr/bin/env python3
"""
engagement_check.py — scriptable checks for on-site engagement:
above-fold heading extraction, CTA candidate extraction, approximate
load timing, mobile viewport check, help/chat widget detection, and a
readability score for the main body text.

This intentionally implements Flesch Reading Ease by hand (no textstat
dependency) so the script has zero dependencies beyond requests +
beautifulsoup4, which crawl-render-audit already requires.

Usage:
    python engagement_check.py https://example.com
"""
import sys
import re
import json
import time
import argparse

import requests
from bs4 import BeautifulSoup

TIMEOUT = 15
HEADERS = {"User-Agent": "brand-ai-readiness-audit/1.0 (read-only audit bot)"}

CTA_VERBS = re.compile(
    r"\b(get started|sign up|buy|shop|add to cart|contact|book|schedule|"
    r"start|try|subscribe|download|request|learn more|see pricing|"
    r"apply|join|order|get a quote)\b", re.I
)

CHAT_WIDGET_HINTS = [
    "intercom", "drift.com", "zendesk", "livechatinc", "crisp.chat",
    "hubspot", "tawk.to", "olark", "zopim",
]


def fetch_timed(url):
    start = time.perf_counter()
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as e:
        return None, None, None
    ttfb_proxy = resp.elapsed.total_seconds()  # requests' elapsed = time to receive full response headers+body for non-streamed GET
    total = time.perf_counter() - start
    return resp, ttfb_proxy, total


def count_syllables(word):
    word = word.lower()
    word = re.sub(r"[^a-z]", "", word)
    if not word:
        return 0
    vowels = "aeiouy"
    count = 0
    prev_was_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_was_vowel:
            count += 1
        prev_was_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def flesch_reading_ease(text):
    sentences = re.split(r"[.!?]+", text)
    sentences = [s for s in sentences if s.strip()]
    words = re.findall(r"[A-Za-z']+", text)
    if not sentences or not words:
        return None
    syllables = sum(count_syllables(w) for w in words)
    n_sentences = len(sentences)
    n_words = len(words)
    score = 206.835 - 1.015 * (n_words / n_sentences) - 84.6 * (syllables / n_words)
    return round(score, 1)


def check_above_fold_and_cta(soup, page):
    findings = []
    h1 = soup.find("h1")
    hero_text = ""
    if h1:
        hero_text = h1.get_text(" ", strip=True)
        sib_text = []
        for sib in h1.find_all_next(limit=6):
            if sib.name in ("p", "h2", "span", "div") and sib.get_text(strip=True):
                sib_text.append(sib.get_text(" ", strip=True))
            if len(" ".join(sib_text)) > 200:
                break
        hero_text = (hero_text + " " + " ".join(sib_text)).strip()
    else:
        findings.append({
            "title": "No <h1> found on landing page",
            "severity": "medium",
            "evidence": f"{page}: no <h1> element present.",
            "affected_urls": [page],
            "category": "engagement",
            "confidence": "high",
            "suggested_action": {"summary": "Add a clear H1 stating what the site/product is.", "priority": "medium"},
        })

    # crude above-fold approximation: first ~1500 chars of body text
    body_text = soup.get_text(" ", strip=True)
    above_fold_slice = body_text[:1500]
    cta_matches = CTA_VERBS.findall(above_fold_slice)
    if not cta_matches:
        findings.append({
            "title": "No clear call-to-action detected near the top of the page",
            "severity": "high",
            "evidence": f"{page}: no CTA-verb phrases (e.g. 'get started', 'contact', 'buy', 'sign up') found in the first ~1500 characters of visible text.",
            "affected_urls": [page],
            "category": "engagement",
            "confidence": "medium",
            "suggested_action": {"summary": "Add a clear, specific CTA above the fold (e.g. 'Get started', 'See pricing') rather than only passive navigation links.", "priority": "high"},
        })

    return findings, hero_text


def check_viewport(soup, page):
    findings = []
    tag = soup.find("meta", attrs={"name": "viewport"})
    if not tag:
        findings.append({
            "title": "Missing mobile viewport meta tag",
            "severity": "high",
            "evidence": f"{page}: no <meta name=\"viewport\"> tag found.",
            "affected_urls": [page],
            "category": "engagement",
            "confidence": "high",
            "suggested_action": {"summary": "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">.", "priority": "high"},
        })
    else:
        content = tag.get("content", "")
        if "user-scalable=no" in content.replace(" ", "").lower() or "maximum-scale=1" in content.replace(" ", "").lower():
            findings.append({
                "title": "Viewport configuration disables pinch-zoom",
                "severity": "medium",
                "evidence": f"{page}: viewport meta content='{content}' disables zoom, hurting mobile accessibility.",
                "affected_urls": [page],
                "category": "engagement",
                "confidence": "high",
                "suggested_action": {"summary": "Remove user-scalable=no / maximum-scale=1 restrictions from the viewport tag.", "priority": "medium"},
            })
    return findings


def check_help_affordance(resp, soup, page):
    findings = []
    html_lower = resp.text.lower()
    has_widget = any(hint in html_lower for hint in CHAT_WIDGET_HINTS)
    contact_link = soup.find("a", string=re.compile(r"contact|help|support", re.I)) or \
        soup.find("a", href=re.compile(r"contact|help|support", re.I))
    if not has_widget and not contact_link:
        findings.append({
            "title": "No help/chat/contact affordance found",
            "severity": "medium",
            "evidence": f"{page}: no known chat-widget script detected and no contact/help/support link found.",
            "affected_urls": [page],
            "category": "engagement",
            "confidence": "medium",
            "suggested_action": {"summary": "Add a visible contact/help link or a chat widget so confused visitors have a path forward.", "priority": "medium"},
        })
    return findings


def check_load_time(ttfb, total, page):
    findings = []
    if ttfb is None:
        return findings
    # Judgment-based, not an arbitrary universal cutoff: flag only clearly slow responses.
    if ttfb > 2.0:
        findings.append({
            "title": "Slow server response time (approximate)",
            "severity": "medium",
            "evidence": f"{page}: response took ~{ttfb:.2f}s server-side (approximate TTFB proxy via plain HTTP GET, no JS/paint timing included).",
            "affected_urls": [page],
            "category": "engagement",
            "confidence": "low",
            "suggested_action": {"summary": "Investigate server/hosting/CDN response time; confirm with real browser Network-tab or PageSpeed Insights measurements before prioritizing.", "priority": "low"},
        })
    return findings


def check_readability(soup, page):
    findings = []
    paragraphs = soup.find_all("p")
    if not paragraphs:
        return findings
    text = " ".join(p.get_text(" ", strip=True) for p in paragraphs)
    if len(text.split()) < 50:
        return findings  # not enough text to score meaningfully
    score = flesch_reading_ease(text)
    long_unbroken = sum(1 for p in paragraphs if len(p.get_text(strip=True)) > 800)
    headings = soup.find_all(re.compile("^h[1-6]$"))
    if score is not None and score < 30 and long_unbroken > 0 and len(headings) < 2:
        findings.append({
            "title": "Dense, low-readability text with no structural breaks",
            "severity": "medium",
            "evidence": f"{page}: Flesch Reading Ease ~{score} (lower = denser), {long_unbroken} very long unbroken paragraph(s), only {len(headings)} heading(s) on the page.",
            "affected_urls": [page],
            "category": "engagement",
            "confidence": "medium",
            "suggested_action": {"summary": "Break up dense paragraphs with subheadings, bullets, or shorter sentences.", "priority": "medium"},
        })
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    args = ap.parse_args()

    resp, ttfb, total = fetch_timed(args.url)
    findings = []
    if resp is None:
        print(json.dumps([{
            "title": "Page unreachable for engagement audit",
            "severity": "critical",
            "evidence": f"GET {args.url} failed.",
            "affected_urls": [args.url],
            "category": "engagement",
            "confidence": "high",
            "suggested_action": {"summary": "Investigate hosting/DNS/SSL issues.", "priority": "high"},
        }], indent=2))
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    fold_findings, hero_text = check_above_fold_and_cta(soup, args.url)
    findings += fold_findings
    findings += check_viewport(soup, args.url)
    findings += check_help_affordance(resp, soup, args.url)
    findings += check_load_time(ttfb, total, args.url)
    findings += check_readability(soup, args.url)

    print(json.dumps(findings, indent=2))


if __name__ == "__main__":
    main()
