"""Download-limit and skipped-coverage regressions, including streamed HTTP."""
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from auditlib.collection import Collector, BudgetExceeded, normalize
from auditlib.runner import audit, parse_args
from test_audit import SITE, response


class DownloadTests(unittest.TestCase):
    def make_collector(self, routes, **kwargs):
        return Collector(transport=lambda url: routes.get(url, response('', 404)), validator=normalize, **kwargs)

    def test_homepage_larger_than_old_cap_is_collected(self):
        html = '<!--' + 'x' * 2_100_000 + '--><main><h1>Documentation</h1><p>Public content.</p></main>'
        c = self.make_collector({SITE+'robots.txt': response(''), SITE: response(html)})
        report = audit(SITE, collector=c, browser=False)
        self.assertEqual(report['run_metadata']['pages_audited'], [SITE])
        self.assertEqual(c.cache[SITE]['bytes_received'], len(html.encode()))
        self.assertEqual(report['run_metadata']['download_budget']['decoded_bytes_received'], c.downloaded_bytes)
        self.assertFalse(report['findings'])

    def test_oversized_body_is_explicit_and_downstream_not_run(self):
        c = self.make_collector({SITE+'robots.txt': response(''), SITE: response('x' * 2000)}, max_response_bytes=1000)
        with patch('auditlib.runner.render_pages') as render:
            report = audit(SITE, collector=c, browser=True)
        render.assert_not_called()
        saved = next(r for r in report['run_metadata']['evidence_store'] if r['url'] == SITE)
        self.assertEqual(saved['state'], 'incomplete')
        self.assertEqual(saved['status'], 200)
        self.assertEqual(saved['limit_scope'], 'per_response')
        self.assertEqual(saved['bytes_received'], 2000)
        self.assertTrue(saved['truncated'])
        self.assertTrue(saved['observed_at'])
        self.assertEqual(report['run_metadata']['pages_audited'], [])
        completed = report['run_metadata']['stages_completed']
        for stage in ('crawl', 'render', 'facts', 'claims', 'engagement'):
            self.assertNotIn(stage, completed)
            self.assertTrue(any(c['check_id'] == 'stage.'+stage and c['status'] == 'not_run' for c in report['checks']))
        self.assertEqual(report['findings'], [])
        self.assertEqual(c.cache[SITE]['body'], b'')

    def test_total_budget_counts_failed_downloads_and_prevents_new_requests(self):
        c = self.make_collector({SITE+'robots.txt': response(''), SITE: response('a'*40), SITE+'next': response('b'*80)},
                                max_response_bytes=100, max_download_bytes=100)
        self.assertEqual(c.fetch(SITE)['state'], 'ok')
        self.assertEqual(c.fetch(SITE+'next')['limit_scope'], 'total_download')
        self.assertEqual(c.downloaded_bytes, 120)
        count = len(c.log)
        with self.assertRaises(BudgetExceeded):
            c.fetch(SITE+'never')
        self.assertEqual(len(c.log), count)
        self.assertEqual(c.fetch(SITE)['state'], 'ok')
        self.assertEqual(c.downloaded_bytes, 120)

    def test_per_response_limit_does_not_exhaust_total_budget(self):
        c = self.make_collector({SITE+'robots.txt': response(''), SITE: response('a'*60), SITE+'small': response('b'*10)},
                                max_response_bytes=50, max_download_bytes=1000)
        self.assertEqual(c.fetch(SITE)['state'], 'incomplete')
        self.assertEqual(c.fetch(SITE+'small')['state'], 'ok')
        self.assertEqual(c.downloaded_bytes, 70)

    def test_partial_robots_is_never_parsed_as_permission(self):
        c = self.make_collector({SITE+'robots.txt': response('User-agent: *\nAllow: /\n'+'x'*100)}, max_response_bytes=30)
        self.assertEqual(c.fetch(SITE)['state'], 'unknown')
        self.assertEqual([r['url'] for r in c.log], [SITE+'robots.txt'])

    def test_streaming_http_enforces_limits_without_content_length(self):
        c = Collector(validator=normalize, max_response_bytes=8, max_download_bytes=100)
        resp = MagicMock()
        resp.__enter__.return_value = resp
        resp.status_code = 200
        resp.headers = {'Content-Type': 'text/html', 'Content-Encoding': 'gzip'}
        resp.elapsed.total_seconds.return_value = .01
        chunks = iter([b'1234', b'5678', b'9', b'never consumed'])
        resp.iter_content.return_value = chunks
        with patch.object(c.session, 'get', return_value=resp):
            result = c.wire(SITE)
        self.assertEqual(result['state'], 'incomplete')
        self.assertEqual(result['bytes_received'], 9)
        self.assertEqual(result['status'], 200)
        self.assertEqual(next(chunks), b'never consumed')
        resp.__exit__.assert_called_once()

    def test_cli_defaults_and_overrides(self):
        default = parse_args([SITE])
        self.assertEqual((default.max_response_mb, default.max_download_mb), (20, 100))
        configured = parse_args([SITE, '--max-response-mb', '40', '--max-download-mb', '150'])
        self.assertEqual((configured.max_response_mb, configured.max_download_mb), (40, 150))
        for value in ('0', '-1', 'nan', 'inf'):
            with patch('sys.stderr', new=io.StringIO()), self.assertRaises(SystemExit):
                parse_args([SITE, '--max-response-mb', value])

    def test_missing_browser_not_marked_completed(self):
        c = self.make_collector({SITE+'robots.txt': response(''), SITE: response('<main>Public content.</main>')})
        report = audit(SITE, collector=c, browser=False)
        self.assertNotIn('render', report['run_metadata']['stages_completed'])


if __name__ == '__main__':
    unittest.main()
