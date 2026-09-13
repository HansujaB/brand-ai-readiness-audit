"""Paired engagement regressions using offline Chromium and deterministic HTTP."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(ROOT/'.browsers'))
from auditlib.browser import OBSERVE, INIT
from auditlib.engagement import engagement_checks, page_purpose, compact_report
from auditlib.diagnostics import Results
from auditlib.runner import audit
from auditlib.collection import BudgetExceeded
from test_audit import page, response, collector, SITE


class EngagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.pw=sync_playwright().start()
        cls.browser=cls.pw.chromium.launch()
        cls.tab=cls.browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def observe(self,html,purpose='product'):
        self.tab.set_content('<meta name="viewport" content="width=device-width,initial-scale=1">'+html)
        return self.tab.evaluate(OBSERVE,{'purpose':purpose})

    def inspect(self,html,reliable=True):
        sample=self.observe(html)
        sample['reliable']=reliable
        p=page(html,SITE+'products/coat');p.rendered={'mobile':sample}
        result=Results();engagement_checks(p,result)
        return result,sample

    def test_disabled_and_aria_disabled_are_not_usable(self):
        for attr in ('disabled','aria-disabled="true"'):
            r,_=self.inspect('<main><button '+attr+'>Buy now</button></main>')
            self.assertEqual(next(c['status'] for c in r.checks if c['check_id']=='journey.actions.mobile'),'unknown')
            self.assertFalse(r.findings) # Could be a legitimate unavailable state.

    def test_transparent_ancestor_and_inert_are_not_visible(self):
        for attr in ('style="opacity:0"','inert','style="visibility:hidden"'):
            _,sample=self.inspect('<main><div '+attr+'><button>Add to cart</button></div></main>')
            self.assertFalse(sample['actions'])

    def test_zoom_restriction_is_declaration_not_browser_claim(self):
        for setting, expected in [('user-scalable=0',True),('maximum-scale=1.5',True),('maximum-scale=10',False)]:
            result=Results();engagement_checks(page('<meta name="viewport" content="'+setting+'"><main>Home</main>'),result)
            self.assertEqual(any(f['check_id']=='journey.zoom' for f in result.findings),expected)

    def test_currency_symbols_remain_valid_unicode(self):
        for currency in ('\u20b9', '\u20ac', '\u00a3', 'USD '):
            r,_=self.inspect('<main><p>'+currency+'99</p></main>')
            self.assertEqual(next(j for j in r.journeys if j['needed_information']=='budget')['status'],'pass')

    def test_aria_disabled_ancestor_is_not_usable(self):
        _,sample=self.inspect('<main><div aria-disabled="true"><button>Add to cart</button></div></main>')
        self.assertFalse(sample['actions'][0]['enabled'])

    def test_add_to_cart_recognized(self):
        r,sample=self.inspect('<main><button>Add to cart</button></main>')
        self.assertTrue(sample['actions'][0]['relevant'])
        self.assertTrue(any(c['check_id']=='journey.actions.mobile' and c['status']=='pass' for c in r.checks))

    def test_unrelated_contact_not_product_action(self):
        _,sample=self.inspect('<main><a href="/contact">Contact</a></main>')
        self.assertFalse(sample['actions'][0]['relevant'])

    def test_101st_action_retained(self):
        sample=self.observe('<main>'+''.join('<a href="#">Help</a> ' for _ in range(100))+'<button>Add to cart</button></main>')
        self.assertTrue(any(a['name']=='Add to cart' for a in sample['actions']))

    def test_css_hidden_answers_never_pass(self):
        r,_=self.inspect('<style>.hidden{display:none}</style><main><p class="hidden">USD 99. Returns within 30 days. Material cotton.</p></main>')
        self.assertTrue(all(j['status']=='unknown' for j in r.journeys))

    def test_coherent_visible_returns_answer_passes(self):
        r,_=self.inspect('<main><p>Returns accepted within 30 days of delivery.</p></main>')
        self.assertEqual(next(j for j in r.journeys if j['needed_information']=='returns')['status'],'pass')

    def test_disconnected_words_do_not_answer_returns(self):
        r,_=self.inspect('<main><p>Returns</p><p>Shipping takes 30 days.</p></main>')
        self.assertEqual(next(j for j in r.journeys if j['needed_information']=='returns')['status'],'unknown')

    def test_partial_render_cannot_create_visual_findings(self):
        r,_=self.inspect('<main><button>Buy now</button></main><div style="position:fixed;inset:0;background:white">Loading</div>',False)
        self.assertFalse(r.findings)
        self.assertFalse(any(c['check_id']=='journey.actions.mobile' and c['status']=='pass' for c in r.checks))

    def test_blocker_identified_with_geometry(self):
        r,_=self.inspect('<main><button id="buy">Buy now</button></main><div id="overlay" style="position:fixed;inset:0;background:white">Overlay</div>')
        f=next(f for f in r.findings if f['check_id']=='journey.obstructed_action')
        self.assertIn('#overlay',f['evidence']);self.assertIn('bounds',f['evidence'])

    def test_partial_viewport_control_is_hit_tested(self):
        _,sample=self.inspect('<main><button style="position:fixed;top:-5px;height:40px">Add to cart</button></main>')
        self.assertTrue(sample['actions'][0]['in_viewport'])

    def test_tables_not_blanket_overflow_defects(self):
        r,_=self.inspect('<main><table style="width:1200px"><tr><td>'+'Table cell '*20+'</td></tr></table></main>')
        self.assertFalse(any(f['check_id']=='journey.horizontal_overflow' for f in r.findings))

    def test_text_overflow_has_locator(self):
        r,_=self.inspect('<main><p id="wide" style="width:1200px">'+'Essential reading '*20+'</p></main>')
        self.assertTrue(any('#wide' in f['evidence'] for f in r.findings))

    def test_material_percentage_and_bestseller_no_noise(self):
        r,_=self.inspect('<main><p>100% cotton. Bestseller dress.</p></main>')
        self.assertFalse(any('citation' in x['suggested_action']['summary'].lower() or 'percentage' in x['suggested_action']['summary'].lower() for x in r.suggestions))

    def test_empty_accessible_name_found(self):
        r,_=self.inspect('<main><button style="width:50px;height:50px"></button></main>')
        self.assertTrue(any(f['check_id']=='journey.unnamed_control' for f in r.findings))

    def test_purpose_ignores_hostname_and_respects_article(self):
        self.assertEqual(page_purpose(page('<main>About</main>','https://shop.example/about-us')),'informational')
        self.assertEqual(page_purpose(page('<main>News</main>',SITE+'blog/product-announcement')),'article')
        self.assertEqual(page_purpose(page('<script type="application/ld+json">{"@type":"Product"}</script>',SITE+'item/dress')),'product')

    def test_question_specific_destination_and_soft_error(self):
        html='<main><a href="/pricing">Pricing</a><a href="/returns">Returns</a></main>'
        p=page(html,SITE+'products/dress')
        c=collector({SITE+'robots.txt':response(''),SITE+'pricing':response('<p>USD 100</p>'),SITE+'returns':response('<p>404 Not Found</p>')})
        result=Results();engagement_checks(p,result,c)
        returns=next(j for j in result.journeys if j['needed_information']=='returns')
        self.assertEqual([x['url'] for x in returns['public_navigation_candidates']],[SITE+'returns'])
        self.assertFalse(returns['destination_answers'][0]['answer_candidate'])
        self.assertEqual(returns['status'],'unknown')

    def test_budget_failure_preserves_static_engagement(self):
        c=collector({SITE+'robots.txt':response(''),SITE:response('<main>Home</main>')})
        with patch('auditlib.runner.render_pages',side_effect=BudgetExceeded('render budget')):
            report=audit(SITE,collector=c,component='engagement')
        self.assertIn('engagement',report['run_metadata']['stages_completed'])
        self.assertTrue(any(c['check_id']=='journey.purpose' for c in report['checks']))

    def test_compact_groups_viewports_and_recounts(self):
        r,_=self.inspect('<main><button id="buy">Buy now</button></main><div id="cover" style="position:fixed;inset:0;background:white">Overlay</div>')
        r.findings+=list(r.findings)
        report={'site':SITE,'audited_at':'2026-09-11T00:00:00Z','findings':r.findings,'checks':r.checks,'proactive_suggestions':[], 'run_metadata':{'pages_audited':[SITE]}}
        compact=compact_report(report)
        self.assertEqual(compact['summary']['total_findings'],1)
        self.assertNotIn('checks',compact)

    def test_get_search_error_is_evidenced_without_post(self):
        html='<main><h1>Coat</h1><form role="search" action="/search" method="get"><input type="search" name="q"></form></main>'
        c=collector({SITE+'robots.txt':response('')})
        result=Results();engagement_checks(page(html,SITE+'products/coat'),result,c)
        self.assertTrue(any(f['check_id']=='journey.broken_search' for f in result.findings))
        self.assertTrue(any(x['url']==SITE+'search?q=Coat' for x in c.log))
        result=Results();c=collector({SITE+'robots.txt':response('')})
        engagement_checks(page(html.replace('method="get"','method="post"'),SITE+'products/coat'),result,c)
        self.assertFalse(c.log)

    def test_product_context_mismatch_is_not_answer(self):
        def html(name):
            return '<script type="application/ld+json">'+json.dumps({'@type':'Product','name':name})+'</script><main><p>Returns within 30 days.</p></main>'
        p=page(html('Coat')+'<a href="/returns">Returns</a>',SITE+'products/coat')
        c=collector({SITE+'robots.txt':response(''),SITE+'returns':response(html('Boots'))})
        result=Results();engagement_checks(p,result,c)
        answer=next(j for j in result.journeys if j['needed_information']=='returns')['destination_answers'][0]
        self.assertEqual(answer['context_status'],'different_product')
        self.assertFalse(answer['answer_candidate'])

    def test_shadow_control_included(self):
        sample=self.observe('<main><div id="host"></div></main><script>document.querySelector("#host").attachShadow({mode:"open"}).innerHTML="<button>Add to cart</button>"</script>')
        self.assertTrue(any(a['name']=='Add to cart' for a in sample['actions']))


if __name__=='__main__':
    unittest.main()
