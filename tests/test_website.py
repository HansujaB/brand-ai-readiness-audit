"""Website-only scope and detection regressions with no public network traffic."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from test_audit import SITE, page, response, collector
from auditlib.runner import audit, parse_args
from auditlib.scope import SiteScope
from auditlib.diagnostics import Results, candidates, stress_tests
from auditlib.engagement import page_purpose, QUESTIONS
from auditlib.freshness import extract_policy_claims, compare_site_claims
from auditlib.reporting import owner_report


class WebsiteScopeTests(unittest.TestCase):
    def test_url_only_uses_full_sampling_and_all_audit_components(self):
        paths=['p/chair','p/table','pricing','returns','delivery','services','support',
               'cat/furniture','docs','about','contact','warranty']
        html='<html lang="en"><main><h1>Furniture shop</h1>'+''.join(
            '<a href="/'+path+'">'+path+'</a>' for path in paths)+'</main></html>'
        routes={SITE+'robots.txt':response(''),SITE:response(html)}
        routes.update({SITE+path:response('<html lang="en"><main><h1>'+path+'</h1><p>Public information.</p></main></html>') for path in paths})
        c=collector(routes)
        with patch('auditlib.runner.render_pages',return_value=False) as render:
            report=audit(SITE,collector=c)
        metadata=report['run_metadata']
        self.assertEqual(len(metadata['pages_audited']),9)
        self.assertNotIn('depth',metadata)
        render.assert_called_once()
        selected,_,_,enabled=render.call_args.args
        self.assertTrue(enabled)
        self.assertEqual(len(selected),3)
        self.assertEqual({p.purpose for p in selected},{'product','pricing','returns'})
        self.assertEqual(set(metadata['stage_status']),{'collection','crawl','render','facts','claims','engagement'})
        self.assertNotIn('not_applicable',metadata['stage_status'].values())
        self.assertEqual(metadata['stage_status']['render'],'not_run')
        self.assertTrue(any(c['check_id']=='stage.render' for c in report['checks']))

    def test_full_audit_keeps_partial_evidence_when_request_budget_runs_out(self):
        html='<main><h1>Store</h1>'+''.join('<a href="/item/'+str(i)+'">Item</a>' for i in range(12))+'</main>'
        routes={SITE+'robots.txt':response(''),SITE:response(html)}
        routes.update({SITE+'item/'+str(i):response('<main>Public information.</main>') for i in range(12)})
        c=collector(routes,max_requests=3)
        with patch('auditlib.runner.render_pages',return_value=False):
            report=audit(SITE,collector=c)
        self.assertEqual(len(c.log),3)
        self.assertEqual(len(report['run_metadata']['pages_audited']),2)
        self.assertEqual(report['run_metadata']['stage_status']['collection'],'partial')
        self.assertIn('could not be verified',owner_report(report)['note'])

    def test_cli_has_no_depth_selector(self):
        args=parse_args([SITE])
        self.assertFalse(hasattr(args,'depth'))
        self.assertFalse(args.no_browser)
        self.assertEqual(args.budget,270)
        for mode in ('quick','basic','standard','deep'):
            with self.subTest(mode=mode), patch('sys.stderr'), self.assertRaises(SystemExit):
                parse_args([SITE,'--depth',mode])

    def test_exact_origin_applies_to_assets_before_and_after_locale_selection(self):
        scope=SiteScope('https://EXAMPLE.com:443/in/en/')
        foreign=['https://www.example.com/', 'https://cdn.example.com/', 'https://other.example/',
                 'http://example.com/', 'https://example.com:80/', 'https://example.com.evil.example/']
        for resolved in (False,True):
            scope.resolved=resolved
            for url in foreign:
                for purpose in ('page','asset','sitemap'):
                    with self.subTest(url=url,purpose=purpose,resolved=resolved):
                        self.assertFalse(scope.allows(url,purpose))
            self.assertTrue(scope.allows(SITE+'shared/app.js','asset'))
            self.assertTrue(scope.allows('https://example.com:443/in/en/'))
        self.assertEqual(scope.as_dict()['origin'],SITE.rstrip('/'))

    def test_origin_redirects_are_rejected_before_address_validation(self):
        for target in ('https://www.example.com/', 'http://example.com/', 'https://example.com:80/', 'https://cdn.example.com/app.js'):
            with self.subTest(target=target):
                c=collector({SITE+'robots.txt':response(''),SITE:response('',302,{'location':target})})
                c.scope=SiteScope(SITE)
                with patch.object(c,'validator',wraps=c.validator) as validate:
                    self.assertEqual(c.fetch(SITE,purpose='asset')['state'],'out_of_scope')
                    self.assertTrue(all(call.args[0].startswith(SITE) for call in validate.call_args_list))
                self.assertEqual([x['url'] for x in c.log],[SITE+'robots.txt',SITE])

    def test_robots_redirect_cannot_leave_origin(self):
        c=collector({SITE+'robots.txt':response('',302,{'location':'https://robots.example.net/robots.txt'})})
        c.scope=SiteScope(SITE)
        with patch.object(c,'validator',wraps=c.validator) as validate:
            self.assertEqual(c.fetch(SITE)['state'],'unknown')
            self.assertTrue(all(call.args[0].startswith(SITE) for call in validate.call_args_list))
        self.assertEqual([x['url'] for x in c.log],[SITE+'robots.txt'])

    def test_foreign_cached_response_cannot_bypass_origin(self):
        c=collector({})
        c.scope=SiteScope(SITE)
        c.cache[SITE]={**response('Foreign content'),'url':'https://cdn.example.com/page','state':'ok'}
        self.assertEqual(c.fetch(SITE)['state'],'out_of_scope')
        self.assertEqual(c.log,[])

    def run_site(self, root, routes, **kwargs):
        c=collector({SITE+'robots.txt':response(''), **routes}, seconds=30)
        r=audit(root, collector=c, browser=False, **kwargs)
        return r,c

    def test_country_and_language_are_inferred_and_other_versions_never_fetched(self):
        root=SITE+'in/en/'
        html='<html lang="en-IN"><main><h1>Shop</h1><a href="/in/en/p/chair">Chair</a><a href="/in/hi/">Hindi</a><a href="/ee/et/">Estonia</a><a href="https://news.example/story">News</a></main></html>'
        r,c=self.run_site(root,{root:response(html),SITE+'in/en/p/chair':response('<html lang="en-IN"><h1>Chair</h1></html>')})
        self.assertEqual(r['run_metadata']['scope']['country'],'IN')
        self.assertEqual(r['run_metadata']['scope']['language'],'en')
        self.assertEqual(set(r['run_metadata']['pages_audited']),{root,SITE+'in/en/p/chair'})
        self.assertFalse(any('/ee/' in x['url'] or '/hi/' in x['url'] or 'news.example' in x['url'] for x in c.log))

    def test_bare_root_selects_one_published_locale(self):
        html='<link rel="alternate" hreflang="x-default" href="/"><link rel="alternate" hreflang="en-IN" href="/in/en/"><link rel="alternate" hreflang="de-DE" href="/de/de/">'
        r,c=self.run_site(SITE,{SITE:response(html),SITE+'de/de/':response('<html lang="de-DE"><h1>Shop</h1></html>')})
        self.assertEqual(r['run_metadata']['scope']['country'],'DE')
        self.assertEqual(r['run_metadata']['pages_audited'],[SITE+'de/de/'])
        self.assertFalse(any('/in/' in x['url'] for x in c.log))

    def test_explicit_locale_selects_published_alternate_from_root(self):
        html='<html lang="en-US"><link hreflang="hi-IN" href="/in/hi/"><link hreflang="en-US" href="/us/en/"></html>'
        r,c=self.run_site(SITE,{SITE:response(html),SITE+'in/hi/':response('<html lang="hi-IN"><h1>Store</h1></html>')},country='IN',language='hi')
        self.assertEqual(r['run_metadata']['pages_audited'],[SITE+'in/hi/'])
        self.assertFalse(any('/us/' in x['url'] for x in c.log))

    def test_foreign_locale_links_and_sitemaps_never_expand_origin(self):
        html='<html lang="en"><link hreflang="en-IN" href="https://www.example.com/in/en/"><a href="https://cdn.example.com/about">About</a></html>'
        r,c=self.run_site(SITE,{SITE:response(html),SITE+'robots.txt':response('Sitemap: https://cdn.example.com/sitemap.xml')})
        self.assertEqual(r['run_metadata']['pages_audited'],[SITE])
        self.assertIsNone(r['run_metadata']['scope']['country'])
        self.assertTrue(all(x['url'].startswith(SITE) for x in c.log))

    def test_generic_site_without_country_path_still_collects_normal_links(self):
        r,c=self.run_site(SITE,{SITE:response('<html lang="en"><a href="/about">About</a></html>'),SITE+'about':response('<html lang="en">About us</html>')})
        self.assertEqual(len(r['run_metadata']['pages_audited']),2)
        self.assertIsNone(r['run_metadata']['scope']['country'])
        self.assertEqual(r['run_metadata']['scope']['language'],'en')

    def test_redirect_cannot_escape_country_or_website(self):
        root=SITE+'in/en/'
        html='<html lang="en-IN"><a href="/in/en/a">A</a><a href="/in/en/b">B</a></html>'
        r,c=self.run_site(root,{root:response(html),SITE+'in/en/a':response('',302,{'location':SITE+'ee/et/'}),SITE+'in/en/b':response('',302,{'location':'https://news.example/story'})})
        self.assertFalse(any('/ee/' in x['url'] or 'news.example' in x['url'] for x in c.log))

    def test_locale_sitemaps_are_filtered_before_download(self):
        root=SITE+'in/en/'
        index='<sitemapindex><sitemap><loc>'+SITE+'ee/et/sitemap.xml</loc></sitemap><sitemap><loc>'+SITE+'in/en/sitemap.xml</loc></sitemap></sitemapindex>'
        r,c=self.run_site(root,{root:response('<html lang="en-IN"><h1>Store</h1></html>'),SITE+'sitemap.xml':response(index),SITE+'in/en/sitemap.xml':response('<urlset><url><loc>'+root+'p/a</loc></url></urlset>'),root+'p/a':response('<html lang="en-IN"><h1>Chair</h1></html>')})
        self.assertIn(root+'p/a',r['run_metadata']['pages_audited'])
        self.assertFalse(any('/ee/' in x['url'] for x in c.log))

    def test_large_discovery_is_bounded_and_does_not_spend_global_download_budget(self):
        r,c=self.run_site(SITE,{SITE:response('<h1>Store</h1>'),SITE+'sitemap.xml':response('x'*3_000_000)})
        self.assertLess(c.downloaded_bytes,2_020_000)
        self.assertEqual(c.cache[SITE+'sitemap.xml']['limit_scope'],'stage_download')
        self.assertEqual(c.fetch(SITE+'another')['status'],404)

    def test_mismatched_document_language_is_excluded(self):
        root=SITE+'in/en/'
        r,c=self.run_site(root,{root:response('<html lang="en-IN"><a href="/in/en/wrong">Wrong</a></html>'),root+'wrong':response('<html lang="hi-IN"><h1>Wrong language</h1></html>')})
        self.assertEqual(r['run_metadata']['pages_audited'],[root])
        self.assertTrue(any(x['check_id']=='collection.locale' for x in r['checks']))

    def test_main_catalog_links_reach_products_before_footer_support(self):
        root='<nav><a href="/help">Help</a><a href="/cat/all">All</a></nav><main><h1>Furniture</h1><a href="/cat/chairs">Chairs</a><a href="/returns">Returns</a></main>'
        category='<main><h1>Chairs</h1><a href="/p/chair">Chair</a></main>'
        product='<main><h1>Chair</h1><p>INR 999</p><a href="/p/other">Other item</a><a href="/returns">Returns</a></main>'
        r,c=self.run_site(SITE,{SITE:response(root),SITE+'cat/chairs':response(category),SITE+'p/chair':response(product),SITE+'returns':response('<main><h1>Returns</h1><p>Returns within 30 days.</p></main>'),SITE+'help':response('<main>Help</main>')})
        pages=r['run_metadata']['pages_audited']
        self.assertEqual(pages[:4],[SITE,SITE+'cat/chairs',SITE+'p/chair',SITE+'returns'])

    def test_cli_has_single_locale_and_no_external_import(self):
        args=parse_args([SITE,'--country','IN','--language','hi','--max-requests','250'])
        self.assertEqual((args.country,args.language,args.max_requests),('IN','hi',250))
        with patch('sys.stderr'), self.assertRaises(SystemExit):
            parse_args([SITE,'--search-results','sources.json'])


class WebsiteReasoningTests(unittest.TestCase):
    def policy(self, text, suffix):
        p=page('<main><h1>Policy</h1><p>'+text+'</p></main>',SITE+suffix)
        p.audit_scope={'country':'IN','language':'en'}
        return extract_policy_claims(p,'Brand')

    def test_prose_delivery_conflict_has_two_source_spans(self):
        r=Results();compare_site_claims(self.policy('Delivery in Delhi takes 7 days.','delivery')+self.policy('Delivery in Delhi takes 10 days.','help'),r)
        self.assertEqual(len(r.findings),1)
        self.assertEqual(len(r.findings[0]['evidence_items']),2)
        self.assertIn('Delhi',r.findings[0]['evidence'])

    def test_different_policy_conditions_are_reviewed_without_false_contradiction(self):
        r=Results();compare_site_claims(self.policy('Returns accepted within 30 days for furniture.','returns')+self.policy('Returns accepted within 14 days for textiles.','help'),r)
        self.assertFalse(r.findings)
        self.assertEqual(len(r.reviews),1)
        self.assertTrue(r.reviews[0]['next_step'])

    def test_historical_policy_is_not_current_conflict(self):
        r=Results();compare_site_claims(self.policy('Previously delivery took 7 days.','delivery')+self.policy('Delivery takes 10 days.','help'),r)
        self.assertFalse(r.findings)
        self.assertEqual(r.comparisons[0]['status'],'historical_difference')

    def test_automatic_fact_check_detects_separated_applicable_terms(self):
        p=page('<main><section><h1>Starter</h1><p>INR 999 per month.</p></section><section><h2>Conditions</h2><p>Available in India only. Billed annually.</p></section></main>')
        r=Results();stress_tests([p],candidates([p],'Brand',None),'Brand',r)
        self.assertTrue(any(f['check_id']=='facts.context_loss' for f in r.findings))
        self.assertIn('Billed annually',r.findings[0]['evidence'])

    def test_other_offers_conditions_do_not_qualify_the_first_price(self):
        p=page('<main><h1>Starter</h1><p>INR 999 per month.</p><h2>Enterprise</h2><p>INR 1999 per month.</p><p>Minimum 10 seats only.</p></main>')
        r=Results();stress_tests([p],candidates([p],'Brand',None),'Brand',r)
        starter=next(f for f in r.fact_tests if 'Starter' in f['question'])
        self.assertEqual(starter['missing_context'],{})

    def test_delivery_service_headings_prevent_false_conflict(self):
        a=page('<main><h1>Express delivery</h1><p>Delivery takes 2 days.</p></main>',SITE+'express')
        b=page('<main><h1>Standard delivery</h1><p>Delivery takes 7 days.</p></main>',SITE+'standard')
        r=Results();compare_site_claims(extract_policy_claims(a,'Brand')+extract_policy_claims(b,'Brand'),r)
        self.assertFalse(r.findings)
        self.assertTrue(r.reviews)

    def test_finalizer_rejects_stale_counts_and_repairs_reviewed_report(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('report_validator',Path('skills/audit-orchestrator/scripts/validate_report.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        r=Results();r.finding('content.example',SITE,'Observed issue','Published evidence','Correct the affected statement','Verify the statement')
        owner=owner_report({'site':SITE,'audited_at':'now','findings':r.findings,'checks':[],'run_metadata':{'pages_audited':[SITE]}})
        owner['summary']['total_findings']=99
        with self.assertRaises(ValueError):module.validate(owner)
        module.validate(owner,repair=True)
        self.assertEqual(owner['summary']['total_findings'],1)
        owner['findings'][0]['evidence']=''
        import jsonschema
        with self.assertRaises(jsonschema.ValidationError):module.validate(owner)

    def test_regional_homepage_policy_support_and_short_product_paths_have_questions(self):
        for suffix, expected in [('in/en/','homepage'),('in/en/p/chair/','product'),('in/en/customer-service/returns/','returns'),('delivery/','delivery'),('help/','support')]:
            purpose=page_purpose(page('<h1>Information</h1>',SITE+suffix))
            self.assertEqual(purpose,expected)
            self.assertTrue(QUESTIONS[purpose])

    def test_owner_output_keeps_three_prioritized_improvements_with_short_evidence(self):
        r=Results()
        for i in range(5):
            r.suggest('content.'+str(i),SITE+str(i),'Observed qualifying condition','Improve this content','Verify this exact question',priority='high' if i==0 else 'medium')
        report={'site':SITE,'audited_at':'now','findings':[],'checks':[],'proactive_suggestions':r.suggestions,'run_metadata':{'pages_audited':[SITE]}}
        owner=owner_report(report)
        self.assertEqual(len(owner['improvements']),3)
        self.assertEqual(owner['improvements'][0]['priority'],'high')
        self.assertTrue(all(set(a)=={'summary','priority','evidence','page','verification'} for a in owner['improvements']))
        self.assertEqual(owner['improvements_summary'],{'total_improvements':3,'critical':0,'high':1,'medium':2,'low':0})
        self.assertEqual(owner['summary']['total_findings'],0)
        import jsonschema
        schema=json.loads(Path('skills/audit-orchestrator/references/owner.schema.json').read_text(encoding='utf-8'))
        jsonschema.validate(owner,schema)

    def test_optional_observations_do_not_force_partial_execution(self):
        r={'site':SITE,'audited_at':'now','findings':[],'checks':[{'check_id':'performance.field','status':'not_applicable'}],'run_metadata':{'pages_audited':[SITE],'stage_status':{'collection':'sampled'}}}
        self.assertEqual(set(owner_report(r)),{'site','audited_at','summary','improvements_summary','findings'})


if __name__=='__main__':
    unittest.main()
