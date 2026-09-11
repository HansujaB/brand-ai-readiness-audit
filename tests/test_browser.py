"""Real Chromium paired checks with a deterministic, offline transport."""
import os
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if (ROOT / '.browsers').exists():
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT / '.browsers'))
from auditlib.engagement import engagement_checks
from auditlib.browser import render_pages
from auditlib.diagnostics import Results, stress_tests
from test_audit import collector, response, page, fixture, SITE


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names = ['server_rendered', 'javascript_fact', 'cookie_banner', 'english_action', 'hindi_action', 'obstructed_action']
        cls.pages = {name: page(fixture(name), SITE+name) for name in cls.names}
        prohibited = '<main><h1>Safe</h1></main><script>fetch("/secret");fetch("/submit",{method:"POST",body:"test"});</script>'
        cls.pages['prohibited'] = page(prohibited, SITE+'prohibited')
        routes = {SITE+'robots.txt': response('User-agent: *\nDisallow: /secret'),
                  **{p.url: response(str(p.soup)) for p in cls.pages.values()}}
        interactive='<main><details><summary>Returns</summary><p>Returns within 30 days.</p></details><button id="menu" aria-label="Menu" aria-expanded="false" aria-controls="navigation">Menu</button><nav id="navigation">Links</nav></main><script>document.querySelector("#menu").onclick=function(){this.setAttribute("aria-expanded",this.getAttribute("aria-expanded")!=="true")};</script>'
        cls.pages['disclosures']=page(interactive,SITE+'disclosures')
        routes[SITE+'disclosures']=response(interactive)
        redirected='<main><p id="result">Waiting</p></main><script>fetch("/old-endpoint").then(r=>document.querySelector("#result").textContent=r.url)</script>'
        cls.pages['redirected']=page(redirected,SITE+'redirected')
        routes[SITE+'redirected']=response(redirected)
        routes[SITE+'old-endpoint']=response('',302,{'location':SITE+'new-endpoint'})
        routes[SITE+'new-endpoint']=response('done')
        cls.collector = collector(routes, seconds=120)
        cls.results = Results()
        if not render_pages(list(cls.pages.values()), cls.collector, cls.results):
            raise unittest.SkipTest('Playwright/Chromium unavailable: ' + str(cls.results.checks[:1]))

    def test_price_render_gap_pair(self):
        findings = self.results.findings
        self.assertFalse(any(f['resource'] == SITE+'javascript_fact' for f in findings))
        self.assertTrue(any(c['resource'] == SITE+'javascript_fact' and c['check_id'].startswith('render.essential_fact.') and c['status']=='unknown' for c in self.results.checks))
        self.assertFalse(any(f['resource'] == SITE+'server_rendered' for f in findings))

    def test_cookie_banner_does_not_create_render_gap(self):
        self.assertFalse(any(f['resource'] == SITE+'cookie_banner' for f in self.results.findings))

    def test_english_and_hindi_actions(self):
        for name in ('english_action', 'hindi_action'):
            p = self.pages[name]
            self.assertEqual(set(p.rendered), {'desktop', 'mobile'})
            self.assertTrue(all(any(a['relevant'] and a['in_viewport'] and not a['obstructed'] for a in r['actions']) for r in p.rendered.values()))

    def test_obstructed_action_is_observed(self):
        results = Results()
        engagement_checks(self.pages['obstructed_action'], results)
        self.assertTrue(any(f['check_id'] == 'journey.obstructed_action' for f in results.findings))

    def test_denied_resources_and_post_never_reach_transport(self):
        requested = [r['url'] for r in self.collector.log]
        self.assertNotIn(SITE+'secret', requested)
        self.assertNotIn(SITE+'submit', requested)
        self.assertTrue(all(r['method'] == 'GET' for r in self.collector.log))
        self.assertTrue(self.pages['prohibited'].rendered['desktop']['blocked_requests'])

    def test_supplied_price_target_deduplicates_render_evidence(self):
        from auditlib.runner import merge_findings
        results=Results()
        p=self.pages['javascript_fact']
        results.findings=[f for f in self.results.findings if f['resource']==p.url]
        stress_tests([p],[{'question':'Cost?', 'terms':['₹999'], 'source_url':p.url}],'Acme',results)
        self.assertEqual(len(merge_findings(results.findings)),1)

    def test_redirect_is_cached_and_browser_coverage_is_explicitly_partial(self):
        for sample in self.pages['redirected'].rendered.values():
            self.assertFalse(sample['reliable'])
            self.assertTrue(any('final evidence is cached' in b['reason'] for b in sample['blocked_requests']))
        self.assertIn(SITE+'new-endpoint', self.collector.cache)

    def test_native_disclosure_does_not_submit_forms(self):
        samples=self.pages['disclosures'].rendered
        self.assertEqual(set(samples),{'desktop','mobile'})
        self.assertTrue(all(s['disclosures'] for s in samples.values()))
        self.assertTrue(all(any(d.get('control')=='Menu' and d.get('before') != d.get('after') for d in s['disclosures']) for s in samples.values()))
        self.assertTrue(all(any(d.get('status')=='observed' for d in s['disclosures']) for s in samples.values()))

    def test_metadata_snapshot_contains_injected_directives(self):
        from auditlib.crawl import metadata_checks
        from auditlib.diagnostics import Page
        from playwright.sync_api import sync_playwright
        from auditlib.browser import OBSERVE
        with sync_playwright() as pw:
            browser=pw.chromium.launch()
            tab=browser.new_page()
            tab.set_content('<main>Hello</main><script>let m=document.createElement("meta");m.name="ROBOTS";m.content="noindex";document.head.append(m)</script>')
            sample=tab.evaluate(OBSERVE, {'width':1280})
            browser.close()
        p=Page({**response(sample['metadata_html']), 'url':SITE})
        r=Results();metadata_checks(p,r,'rendered_desktop')
        self.assertTrue(any(f['check_id']=='access.noindex' for f in r.findings))
        self.assertNotIn('document.createElement',sample['metadata_html'])

    def test_lab_metrics_honestly_unavailable_inp(self):
        for p in self.pages.values():
            for sample in p.rendered.values():
                self.assertIsNone(sample['metrics']['inp_ms'])
                self.assertEqual(sample['metrics']['kind'], 'single_anonymous_lab_observation')


if __name__ == '__main__':
    unittest.main()
