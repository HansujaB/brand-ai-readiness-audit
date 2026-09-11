"""Paired regressions for the crawl/render and orchestration review."""
import copy
import json
import socket
import unittest
from unittest.mock import patch, MagicMock
import requests
from test_audit import page, response, collector, SITE
from auditlib.collection import excluded_url, BudgetExceeded
from auditlib.crawl import metadata_checks, schema_checks, directives
from auditlib.diagnostics import Results, candidates, stress_tests
from auditlib.runner import audit, merge_findings, validate_report
from auditlib.reporting import owner_report
from auditlib.network import PinnedAdapter


class CrawlRegressionTests(unittest.TestCase):
    def inspect(self, html, headers=None):
        p=page(html)
        if headers: p.response['headers'].update(headers)
        r=Results();metadata_checks(p,r);schema_checks(p,r)
        return r

    def test_preview_none_is_not_noindex(self):
        for directive, expected in [('max-image-preview:none',False),('none',True),('noindex',True)]:
            r=self.inspect('<meta name="ROBOTS" content="'+directive+'">')
            self.assertEqual(any(f['check_id']=='access.noindex' for f in r.findings),expected)

    def test_header_lines_keep_scope(self):
        r=self.inspect('',{'x-robots-tag':['Googlebot: nofollow','Bingbot: noindex','nosnippet']})
        self.assertEqual([f['entity'] for f in r.findings],['bingbot'])
        self.assertTrue(any(c['check_id']=='access.preview' for c in r.checks))
        self.assertEqual(list(directives('max-image-preview:none')), [('*','max-image-preview','none')])

    def test_canonical_and_section_preview(self):
        r=self.inspect('<link rel="canonical" href="/a"><link rel="canonical" href="/b"><p data-nosnippet>Secret preview</p>')
        self.assertIn('access.canonical_conflict',[f['check_id'] for f in r.findings])
        self.assertIn('access.preview_sections',[c['check_id'] for c in r.checks])
        self.assertFalse(self.inspect('<link rel="canonical" href="/other">').findings)

    def product(self, price='99', currency='USD', visible='USD 99'):
        node={'@type':'Product','name':'Coat','offers':{'@type':'Offer','price':price,'priceCurrency':currency}}
        return '<script type="application/ld+json">'+json.dumps(node)+'</script><main><h1>Coat</h1><span data-product-price>'+visible+'</span></main>'

    def test_shipping_not_product_price(self):
        r=self.inspect(self.product().replace('<span data-product-price>USD 99</span>','<p>Shipping USD 10</p>'))
        self.assertFalse(r.findings)
        self.assertTrue(any(c['check_id']=='schema.visible_price' and c['status']=='unknown' for c in r.checks))

    def test_currency_and_amount_both_compared(self):
        self.assertFalse(self.inspect(self.product()).findings)
        for text in ('EUR 99','USD 10'):
            self.assertIn('schema.visible_price',[f['check_id'] for f in self.inspect(self.product(visible=text)).findings])

    def test_invalid_price_does_not_throw(self):
        for value in ('9.9.9',{},[],True,'NaN'):
            self.assertIn('schema.invalid_price',[f['check_id'] for f in self.inspect(self.product(price=value)).findings])

    def test_nested_markup_preserves_repeated_offers(self):
        html='<div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Coat</span>'
        html+=''.join('<div itemprop="offers" itemscope itemtype="https://schema.org/Offer"><meta itemprop="price" content="'+x+'"><meta itemprop="priceCurrency" content="USD"></div>' for x in ('99','109'))+'</div>'
        p=page(html);product=next(n for n in p.nodes if n['@type']=='Product')
        self.assertEqual([o['price'] for o in product['offers']],['99','109'])
        self.assertNotIn('price',product)

    def test_base_and_noscript_preserved(self):
        p=page('<base href="/docs/"><a href="guide">Guide</a><noscript><p>USD 99 fallback</p></noscript>')
        self.assertEqual(p.links[0]['url'],SITE+'docs/guide')
        self.assertIn('USD 99',p.accessible_text)

    def test_no_question_words_as_evidence(self):
        self.assertEqual(candidates([], 'Shop', ['What is the price?'])[0]['terms'],[])

    def test_same_price_different_entities_retained(self):
        p=page('<main><section><h2>Coat</h2><p>USD 99</p></section><section><h2>Boots</h2><p>USD 99</p></section></main>')
        self.assertEqual(len(candidates([p],'Shop',None)),2)

    def test_footer_condition_not_associated(self):
        p=page('<main><h1>Coat</h1><p>USD 99</p></main><footer>Newsletter only available in Canada</footer>')
        r=Results();stress_tests([p],[{'question':'Price?', 'terms':['USD 99']}],'Shop',r)
        self.assertFalse(r.findings)
        self.assertIsNone(r.fact_tests[0]['dimensions']['exceptions']['expected'])

    def test_partial_render_cannot_prove_missing_fact(self):
        p=page('<main>Loading</main>');p.rendered={'desktop':{'text':'USD 99','blocks':['USD 99'],'reliable':False}}
        r=Results();stress_tests([p],[{'question':'Price?','terms':['USD 99']}],'Shop',r)
        self.assertFalse(r.findings)
        self.assertEqual(r.fact_tests[0]['status'],'unknown')

    def test_encoded_actions_and_public_api(self):
        for path in ('%61dmin','%2561dmin','x/../checkout','%2Fadmin','admin/settings'):
            self.assertTrue(excluded_url(SITE+path),path)
        self.assertFalse(excluded_url(SITE+'api/catalog'))

    def test_dns_connection_is_pinned_and_tls_hostname_retained(self):
        pool=MagicMock();pool.urlopen.return_value=MagicMock(status=200,headers={})
        address=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))]
        with patch('auditlib.network.socket.getaddrinfo',return_value=address), patch('auditlib.network.urllib3.HTTPSConnectionPool',return_value=pool) as factory:
            adapter=PinnedAdapter();adapter.send(requests.Request('GET',SITE).prepare(),timeout=2)
            self.assertEqual(factory.call_args.args[0],'93.184.216.34')
            self.assertEqual(factory.call_args.kwargs['server_hostname'],'example.com')
            self.assertEqual(factory.call_args.kwargs['assert_hostname'],'example.com')
            self.assertEqual(pool.urlopen.call_args.kwargs['headers']['Host'],'example.com')
        address[0]=(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))
        with patch('auditlib.network.socket.getaddrinfo',return_value=address):
            with self.assertRaises(ValueError): PinnedAdapter().send(requests.Request('GET',SITE).prepare())


class OrchestratorRegressionTests(unittest.TestCase):
    def test_homepage_redirect_origin_and_aliases(self):
        other='https://www.example.com/'
        c=collector({SITE+'robots.txt':response(''),SITE:response('',302,{'location':other}),other+'robots.txt':response(''),other:response('<a href="/a">A</a><a href="/alias">Alias</a><a href="/b">B</a>'),other+'a':response('A'),other+'alias':response('',302,{'location':other+'a'}),other+'b':response('B')})
        r=audit(SITE,collector=c,browser=False)
        self.assertEqual(set(r['run_metadata']['pages_audited']),{other,other+'a',other+'b'})

    def test_failed_attempt_does_not_consume_page_slot(self):
        c=collector({SITE+'robots.txt':response(''),SITE:response('<a href="/missing">Missing</a><a href="/valid">Valid</a>'),SITE+'valid':response('Good')})
        r=audit(SITE,collector=c,browser=False)
        self.assertIn(SITE+'valid',r['run_metadata']['pages_audited'])

    def test_sitemap_only_page_and_bad_child(self):
        c=collector({SITE+'robots.txt':response(''),SITE:response('<h1>Home</h1>'),SITE+'sitemap.xml':response('<sitemapindex><sitemap><loc>'+SITE+'bad.xml</loc></sitemap><sitemap><loc>'+SITE+'good.xml</loc></sitemap></sitemapindex>'),SITE+'bad.xml':response('<html/>'),SITE+'good.xml':response('<urlset><url><loc>'+SITE+'hidden</loc></url></urlset>'),SITE+'hidden':response('Valid')})
        r=audit(SITE,collector=c,browser=False)
        self.assertIn(SITE+'hidden',r['run_metadata']['pages_audited'])
        self.assertTrue(any(f['resource']==SITE+'bad.xml' for f in r['findings']))

    def test_invalid_link_and_page_error_are_isolated(self):
        c=collector({SITE+'robots.txt':response(''),SITE:response('<a href="https://example.com:bad/a">Bad</a><a href="/good">Good</a>'),SITE+'good':response('Good')})
        with patch('auditlib.runner.check_freshness',side_effect=ValueError('bad markup')):
            r=audit(SITE,collector=c,browser=False)
        self.assertIn(SITE+'good',r['run_metadata']['pages_audited'])
        self.assertTrue(any(x['check_id']=='journey.purpose' for x in r['checks']))

    def test_crawl_is_checkpointed_before_browser_termination(self):
        c=collector({SITE+'robots.txt':response(''),SITE:response('<meta name="robots" content="noindex">')})
        saved=[]
        with patch('auditlib.runner.render_pages',side_effect=SystemExit('killed')):
            with self.assertRaises(SystemExit): audit(SITE,collector=c,checkpoint=lambda r:saved.append(copy.deepcopy(r)))
        self.assertTrue(any(f['check_id']=='access.noindex' for f in saved[-1]['findings']))

    def test_phase_budget_does_not_consume_next_phase(self):
        c=collector({SITE+'robots.txt':response(''),SITE:response('OK')})
        with c.allowance(1,0):
            with self.assertRaises(BudgetExceeded): c.fetch(SITE)
        self.assertEqual(c.fetch(SITE)['state'],'ok')

    def test_merge_priority_identity_and_owner_explanation(self):
        r=Results()
        r.finding('x',SITE,'Issue','Owner explanation','fix','verify',severity='low',root_cause='a')
        r.finding('x',SITE,'Issue','Worse evidence','fix now','verify',severity='high',root_cause='a')
        r.finding('x',SITE,'Other cause','Second explanation','fix','verify',root_cause='b')
        merged=merge_findings(r.findings)
        self.assertEqual(len(merged),2)
        self.assertEqual(merged[0]['suggested_action']['priority'],'high')
        report={'site':SITE,'audited_at':'now','findings':r.findings,'checks':[{'status':'not_run','check_id':'external.search'}],'run_metadata':{'pages_audited':[SITE]}}
        compact=owner_report(report)
        self.assertEqual(compact['coverage']['status'],'partial')
        self.assertIn('Worse evidence',compact['findings'][0]['evidence'])
        self.assertEqual([f['id'] for f in compact['findings']],[f['id'] for f in merged])

    def test_audit_exclusion_is_coverage_only(self):
        c=collector({SITE+'robots.txt':response('User-agent: BrandReadinessAudit\nDisallow: /')})
        r=audit(SITE,collector=c,browser=False)
        self.assertFalse(r['findings'])
        self.assertEqual(owner_report(r)['coverage']['status'],'partial')

    def test_nested_diagnostic_schema_rejects_invalid_array_item(self):
        import jsonschema
        r=audit(SITE,collector=collector({SITE+'robots.txt':response(''),SITE:response('OK')}),browser=False)
        r['claims']=['not a claim']
        with self.assertRaises(jsonschema.ValidationError):validate_report(r)


if __name__=='__main__':unittest.main()
