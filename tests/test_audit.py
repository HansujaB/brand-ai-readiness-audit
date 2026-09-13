"""Paired diagnostic regression tests. No public network requests."""
import copy
import io
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from auditlib.collection import Collector, Robots, BudgetExceeded, normalize, public_url
from auditlib.diagnostics import Page, Results, crawl_checks, stress_tests, pdf_check
from auditlib.runner import audit, merge_findings, validate_report

SITE = 'https://example.com/'


def response(body='', status=200, headers=None):
    return {'status': status, 'body': body.encode() if isinstance(body, str) else body,
            'headers': headers or {'content-type': 'text/html'}}


def collector(routes, seconds=30, max_requests=80):
    def transport(url):
        return routes.get(url, response('', 404))
    return Collector(seconds, max_requests, transport=transport, validator=normalize)


def page(html, url=SITE):
    return Page({**response(html), 'url': url, 'observed_at': '2026-09-10T00:00:00Z'})


def fixture(name):
    return (ROOT / 'tests/fixtures' / (name + '.html')).read_text(encoding='utf-8')


class SafetyTests(unittest.TestCase):
    def test_training_exclusion_does_not_block_search(self):
        policy = Robots('User-agent: GPTBot\nDisallow: /\nUser-agent: OAI-SearchBot\nAllow: /')
        self.assertFalse(policy.decision('GPTBot', SITE)[0])
        self.assertTrue(policy.decision('OAI-SearchBot', SITE)[0])

    def test_longest_rule_allow_tie_and_merged_groups(self):
        policy = Robots('User-agent: *\nDisallow: /\nAllow: /public\nDisallow: /public/private*\nAllow: /public/private/open$\nUser-agent: *\nAllow: /another')
        self.assertTrue(policy.decision('audit', SITE + 'public')[0])
        self.assertFalse(policy.decision('audit', SITE + 'public/private/a')[0])
        self.assertTrue(policy.decision('audit', SITE + 'public/private/open')[0])
        self.assertTrue(policy.decision('audit', SITE + 'another')[0])
        self.assertTrue(Robots('User-agent: *\nDisallow: /a\nAllow: /a').decision('x', SITE+'a')[0])

    def test_empty_group_does_not_inherit_later_group(self):
        policy = Robots('User-agent: SafeBot\nDisallow:\nUser-agent: OtherBot\nDisallow: /')
        self.assertTrue(policy.decision('SafeBot', SITE)[0])
        self.assertFalse(policy.decision('OtherBot', SITE)[0])

    def test_encoded_paths(self):
        policy = Robots('User-agent: *\nDisallow: /caf%C3%A9\nDisallow: /private')
        self.assertFalse(policy.decision('x', SITE + 'café')[0])
        self.assertFalse(policy.decision('x', SITE + '%70rivate')[0])

    def test_homepage_blocked_before_discovery(self):
        c = collector({SITE+'robots.txt': response('User-agent: *\nDisallow: /')})
        r = audit(SITE, collector=c, browser=False)
        self.assertEqual([x['url'] for x in c.log], [SITE+'robots.txt'])
        self.assertEqual(r['run_metadata']['pages_audited'], [])

    def test_redirect_permission_checked(self):
        c = collector({SITE+'robots.txt': response('User-agent: *\nDisallow: /secret'),
                       SITE: response('', 302, {'location': '/secret'})})
        self.assertEqual(c.fetch(SITE)['state'], 'blocked')
        self.assertNotIn(SITE+'secret', [x['url'] for x in c.log])

    def test_cross_origin_redirect_never_fetches_new_robots(self):
        c = collector({SITE+'robots.txt': response(''), SITE: response('', 302, {'location': 'https://other.example/hidden'}),
                       'https://other.example/robots.txt': response('User-agent: *\nDisallow: /')})
        self.assertEqual(c.fetch(SITE)['state'], 'out_of_scope')
        self.assertEqual([x['url'] for x in c.log], [SITE+'robots.txt', SITE])

    def test_unknown_robots_fails_closed(self):
        for status in (429, 500, 503):
            c = collector({SITE+'robots.txt': response('', status)})
            self.assertEqual(c.fetch(SITE)['state'], 'unknown')
            self.assertEqual(len(c.log), 1)

    def test_cache_shared_and_budget_enforced(self):
        c = collector({SITE+'robots.txt': response(''), SITE: response('<h1>Works</h1>')})
        c.fetch(SITE)
        c.fetch(SITE)
        self.assertEqual(len(c.log), 2)
        c.deadline = time.monotonic() - 1
        with self.assertRaises(BudgetExceeded):
            c.fetch(SITE+'new')

    def test_request_limit(self):
        c = collector({SITE+'robots.txt': response('')}, max_requests=1)
        with self.assertRaises(BudgetExceeded):
            c.fetch(SITE)

    def test_private_and_transactional_destinations(self):
        for url in ('file:///tmp/a', 'http://user:pass@example.com', 'http://example.com:8000'):
            with self.assertRaises(ValueError):
                normalize(url)
        with self.assertRaises(ValueError):
            public_url('http://127.0.0.1/')
        c = collector({})
        self.assertEqual(c.fetch(SITE+'checkout')['state'], 'unknown')
        self.assertEqual(c.log, [])


class DiagnosticTests(unittest.TestCase):
    def test_nested_schema_and_other_formats(self):
        for name in ('nested_schema', 'microdata', 'rdfa', 'no_schema'):
            p, results = page(fixture(name)), Results()
            crawl_checks(p, results, collector({SITE+'robots.txt': response('')}))
            self.assertFalse([f for f in results.findings if f['check_id'].startswith('schema.')])
        self.assertTrue(any(n.get('@type') == 'Organization' for n in page(fixture('nested_schema')).nodes))

    def test_invalid_schema_is_evidenced(self):
        p, results = page(fixture('invalid_schema')), Results()
        crawl_checks(p, results, collector({SITE+'robots.txt': response('')}))
        self.assertEqual([f['check_id'] for f in results.findings], ['schema.invalid_jsonld'])

    def test_pricing_conditions_paired(self):
        fact = {'question': 'How much is Starter?', 'terms': ['₹999'], 'context': {'billing_period': 'billed annually'}}
        good, bad = Results(), Results()
        stress_tests([page(fixture('conditions_together'))], [fact], 'Acme', good)
        stress_tests([page(fixture('conditions_separate'))], [fact], 'Acme', bad)
        self.assertFalse(good.findings)
        self.assertEqual(bad.findings[0]['check_id'], 'facts.context_loss')
        self.assertTrue(bad.rewrites[0]['all_source_spans_preserved'])
        self.assertEqual(bad.rewrites[0]['missing_after'], [])

    def test_unobserved_fact_is_unknown_not_media_defect(self):
        results = Results()
        stress_tests([page('<img src="a.png"><p>Hello</p>')], [{'question': 'Price?', 'terms': ['₹999']}], 'Acme', results)
        self.assertFalse(results.findings)
        self.assertEqual(results.fact_tests[0]['status'], 'unknown')

    def test_stable_dedup_ignores_titles_and_merges_evidence(self):
        results = Results()
        results.finding('identity.sameas', SITE, 'First title', 'quote', 'fix', 'verify', entity='Acme')
        results.finding('identity.sameas', SITE, 'Different words', 'second quote', 'fix', 'verify', entity='Acme')
        merged = merge_findings(results.findings)
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]['evidence_items']), 2)
        self.assertEqual(merged[0]['id'], merge_findings(list(reversed(results.findings)))[0]['id'])

    def test_missing_browser_not_findings(self):
        c = collector({SITE+'robots.txt': response(''), SITE: response(fixture('no_schema'))})
        report = audit(SITE, collector=c, browser=False)
        validate_report(report)
        self.assertFalse(any(f['check_id'].startswith(('render.', 'performance.')) for f in report['findings']))
        self.assertIn('not_run', [c['status'] for c in report['checks'] if c['check_id'] == 'render.browser'])
        self.assertFalse(report['run_metadata']['capabilities_used']['headless_browser'])

    def test_small_linked_site_without_sitemap(self):
        c = collector({SITE+'robots.txt': response(''), SITE: response('<main><h1>Home</h1><a href="/about">About</a></main>'),
                       SITE+'about': response('<main><h1>About</h1><p>Our story.</p></main>')})
        report = audit(SITE, collector=c, browser=False)
        self.assertEqual(len(report['run_metadata']['pages_audited']), 2)
        self.assertFalse(report['findings'])


    def test_broken_public_information_path(self):
        c = collector({SITE+'robots.txt': response(''), SITE: response('<main><h1>Home</h1><a href="/returns">Return policy</a></main>')})
        c.cache[SITE] = {**response('<main><h1>Product</h1><a href="/returns">Return policy</a></main><script type="application/ld+json">{"@type":"Product"}</script>'), 'url':SITE, 'state':'ok'}
        report = audit(SITE, collector=c, browser=False)
        self.assertTrue(any(f['check_id']=='seo.link_broken' and f['entity']==SITE+'returns' for f in report['findings']))
        self.assertEqual(sum(x['url']==SITE+'returns' for x in c.log), 1)

    def test_automatic_context_dimensions(self):
        r=Results()
        stress_tests([page(fixture('price_999'))],[{'question':'Cost?', 'terms':['₹999']}],'Acme',r)
        dimensions=r.fact_tests[0]['dimensions']
        self.assertTrue(all(dimensions[k]['recoverable'] for k in ('entity','value','unit','billing_period','region','effective_date')))

    def test_pdf_text_and_scanned_or_blank(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        for with_text in (True, False):
            writer = PdfWriter()
            p = writer.add_blank_page(width=300, height=300)
            if with_text:
                font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
                p[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
                stream = DecodedStreamObject()
                stream.set_data(b'BT /F1 12 Tf 30 250 Td (Return within 30 days) Tj ET')
                p[NameObject('/Contents')] = writer._add_object(stream)
            else:
                from pypdf.generic import NumberObject
                image = DecodedStreamObject()
                image.set_data(bytes([0, 0, 0]))
                image.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),
                              NameObject('/Width'):NumberObject(1),NameObject('/Height'):NumberObject(1),
                              NameObject('/ColorSpace'):NameObject('/DeviceRGB'),NameObject('/BitsPerComponent'):NumberObject(8)})
                p[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Im1'):writer._add_object(image)})})
                drawing=DecodedStreamObject();drawing.set_data(b'q 200 0 0 200 20 20 cm /Im1 Do Q')
                p[NameObject('/Contents')]=writer._add_object(drawing)
            stream = io.BytesIO()
            writer.write(stream)
            results = Results()
            pdf_check({**response(stream.getvalue()), 'url': SITE+'policy.pdf'}, results, [])
            self.assertEqual(next(c for c in results.checks if c['check_id'] == 'media.pdf_text')['status'], 'pass' if with_text else 'unknown')
            self.assertFalse(results.findings)


if __name__ == '__main__':
    unittest.main()
