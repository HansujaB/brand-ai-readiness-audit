"""Unseen-site fixtures for broad detection and concise owner output; no network."""
import json
import unittest

from test_audit import SITE, page, response, collector
from auditlib.diagnostics import Results, candidates, stress_tests
from auditlib.discovery import content_checks, link_checks
from auditlib.structured import coverage_checks
from auditlib.scope import SiteScope
from auditlib.runner import audit
from auditlib.reporting import owner_report
from auditlib.freshness import extract_policy_claims, compare_site_claims
from auditlib.identity import identity_checks
from unittest.mock import patch


def document(name='Chair', markup=None, body=''):
    return ('<html lang="en"><head><title>' + name + '</title></head><body><main><h1>' + name +
            '</h1><p>This product includes detailed dimensions and material information.</p>' + body +
            '</main>' + ('<script type="application/ld+json">' + json.dumps(markup) + '</script>' if markup is not None else '') + '</body></html>')


def product(**changes):
    return {'@type':'Product','name':'Chair','image':SITE+'chair.jpg',
            'offers':{'@type':'Offer','price':99,'priceCurrency':'INR'}, **changes}


class StructuredCoverageTests(unittest.TestCase):
    def inspect(self, markup=None, suffix='products/chair'):
        p=page(document(markup=markup),SITE+suffix)
        r=Results();coverage_checks([p],r)
        return p,r

    def test_website_markup_does_not_mask_missing_product_markup(self):
        p,r=self.inspect({'@type':'WebSite','name':'Shop'})
        self.assertEqual([f['check_id'] for f in r.findings],['schema.product_missing'])
        self.assertIn('1 of 1',r.findings[0]['evidence'])
        self.assertEqual(r.findings[0]['severity'],'medium')
        _,fixed=self.inspect(product())
        self.assertFalse(fixed.findings)

    def test_product_cards_do_not_turn_collection_or_homepage_into_product(self):
        for suffix in ('collections/chairs',''):
            p,r=self.inspect(product(),suffix)
            self.assertNotEqual(p.purpose,'product')
            self.assertFalse(r.findings)

    def test_references_and_price_specification_are_resolved(self):
        graph={'@graph':[product(offers={'@id':'#offer'}),
            {'@id':'#offer','@type':'Offer','priceSpecification':{'@id':'#price'}},
            {'@id':'#price','@type':'UnitPriceSpecification','price':0,'priceCurrency':'INR'}]}
        _,r=self.inspect(graph)
        self.assertFalse(r.findings)
        self.assertFalse(r.suggestions)

    def test_review_only_and_aggregate_offer_are_supported(self):
        for node in (product(offers=None,review={'@type':'Review','reviewRating':{'ratingValue':4}}),
                     product(offers={'@type':'AggregateOffer','lowPrice':50,'highPrice':99,'priceCurrency':'INR'})):
            _,r=self.inspect(node)
            self.assertFalse(r.findings)

    def test_missing_properties_are_detected_beyond_valid_json(self):
        for node,field in [(product(name=''), 'name'), (product(offers=None),'offers'),
                           (product(offers={'@type':'Offer','price':'NaN'}),'price'),
                           (product(offers={'@type':'AggregateOffer','lowPrice':99,'highPrice':50,'priceCurrency':'INR'}),'highPrice')]:
            _,r=self.inspect(node)
            self.assertTrue(any(f['check_id']=='schema.product_fields' and field in f['evidence'] for f in r.findings))

    def test_microdata_is_not_reported_as_missing_jsonld(self):
        html=document(body='<div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Chair</span><div itemprop="offers" itemscope itemtype="https://schema.org/Offer"><meta itemprop="price" content="99"><meta itemprop="priceCurrency" content="INR"></div></div>')
        r=Results();coverage_checks([page(html,SITE+'products/chair')],r)
        self.assertFalse(r.findings)

    def test_rendered_markup_prevents_false_absence(self):
        p=page(document(),SITE+'products/chair')
        p.rendered={'desktop':{'metadata_html':'<script type="application/ld+json">'+json.dumps(product())+'</script>'}}
        r=Results();coverage_checks([p],r)
        self.assertFalse(r.findings)

    def test_rdfa_relationships_and_product_group_variants_are_supported(self):
        html=document(body='<div typeof="schema:Product"><span property="schema:name">Chair</span><div rel="schema:offers"><div typeof="schema:Offer"><meta property="schema:price" content="99"><meta property="schema:priceCurrency" content="INR"></div></div></div>')
        r=Results();coverage_checks([page(html,SITE+'products/chair')],r)
        self.assertFalse(r.findings)
        group={'@type':'ProductGroup','name':'Chair','image':SITE+'chair.jpg','hasVariant':[
            product(name='Red chair'),product(name='Blue chair',offers={'@type':'Offer','price':109,'priceCurrency':'INR'})]}
        _,r=self.inspect(group)
        self.assertFalse(r.findings)

    def test_unsupported_markup_reference_is_review_not_missing_field_defect(self):
        html=document(body='<div itemscope itemtype="https://schema.org/Product" itemref="other-fields"><span itemprop="name">Chair</span></div>')
        r=Results();coverage_checks([page(html,SITE+'products/chair')],r)
        self.assertFalse(r.findings)
        self.assertTrue(r.reviews)

    def test_malformed_or_ambiguous_products_require_scope_review(self):
        p=page(document(body='<script type="application/ld+json">{bad}</script>'),SITE+'products/chair')
        r=Results();coverage_checks([p],r)
        self.assertFalse(r.findings)
        self.assertTrue(r.reviews)
        _,r=self.inspect([product(name='Coat'),product(name='Hat')])
        self.assertFalse(r.findings)
        self.assertTrue(r.reviews)

    def test_missing_merchant_details_are_not_basic_snippet_errors(self):
        _,r=self.inspect(product(image=None,offers={'@type':'Offer','price':99}))
        self.assertFalse(r.findings)
        self.assertTrue(any(s['check_id']=='schema.merchant_details' for s in r.suggestions))


class SearchContentTests(unittest.TestCase):
    def test_missing_title_and_description_have_different_classification(self):
        p=page(document().replace('<title>Chair</title>',''),SITE+'products/chair')
        r=Results();content_checks([p],r)
        self.assertTrue(any(f['check_id']=='seo.title_missing' for f in r.findings))
        self.assertTrue(any(s['check_id']=='seo.description_missing' for s in r.suggestions))

    def test_duplicate_titles_group_distinct_pages_but_not_canonical_aliases(self):
        a=page(document(),SITE+'chair');b=page(document(),SITE+'table')
        r=Results();content_checks([a,b],r)
        self.assertEqual(len([f for f in r.findings if f['check_id']=='seo.title_duplicate']),1)
        alias=page(document().replace('</head>','<link rel="canonical" href="/chair"></head>'),SITE+'chair-alias')
        r=Results();content_checks([a,alias],r)
        self.assertFalse(r.findings)

    def test_linked_images_need_names_but_decorative_images_are_allowed(self):
        p=page(document(body='<a href="/chair"><img src="chair.jpg"></a><img src="flourish.png" alt="">'))
        r=Results();content_checks([p],r)
        self.assertTrue(any(f['check_id']=='content.image_link_name' for f in r.findings))
        fixed=page(document(body='<a href="/chair"><img src="chair.jpg" alt="View Chair"></a><img src="flourish.png" alt="">'))
        r=Results();content_checks([fixed],r)
        self.assertFalse(r.findings)
        self.assertFalse(any(s['check_id']=='content.image_alternatives' for s in r.suggestions))

    def test_identity_opportunity_requires_published_name_and_accepts_identified_organization(self):
        p=page(document().replace('</head>','<meta property="og:site_name" content="Acme"></head>'))
        r=Results();identity_checks([p],'Acme',r)
        self.assertTrue(any(s['check_id']=='identity.organization' for s in r.suggestions))
        p=page(document(markup={'@type':'Organization','name':'Acme','url':SITE}))
        r=Results();identity_checks([p],'Acme',r)
        self.assertFalse(r.suggestions)

    def test_conflicting_hreflang_is_checked_without_crawling_other_locales(self):
        html=document().replace('</head>','<link rel="alternate" hreflang="en-IN" href="/one"><link rel="alternate" hreflang="en-IN" href="/two"></head>')
        r=Results();content_checks([page(html)],r)
        self.assertTrue(any(f['check_id']=='seo.hreflang_conflict' for f in r.findings))
        r=Results();content_checks([page(document())],r)
        self.assertFalse(any(f['check_id']=='seo.hreflang_conflict' for f in r.findings))

    def test_failed_link_and_canonical_checks_retain_source_evidence(self):
        p=page(document(body='<a href="/missing">Details</a>').replace('</head>','<link rel="canonical" href="/preferred"></head>'))
        c=collector({SITE+'robots.txt':response(''),SITE+'missing':response('',404),
                     SITE+'preferred':response(document().replace('</head>','<meta name="robots" content="noindex"></head>'))})
        c.scope=SiteScope(SITE)
        r=Results();link_checks([p],c,r)
        self.assertEqual({f['check_id'] for f in r.findings},{'seo.link_broken','seo.canonical_noindex'})
        self.assertTrue(all(f['resource']==SITE for f in r.findings))

    def test_new_link_checks_obey_origin_robots_and_request_bound(self):
        links=''.join('<a href="/detail/'+str(i)+'">Item</a>' for i in range(20))
        links+='<a href="https://other.test/">Outside</a><a href="/private">Private</a>'
        p=page(document(body=links).replace('</head>','<link rel="canonical" href="https://other.test/preferred"></head>'))
        c=collector({SITE+'robots.txt':response('User-agent: *\nDisallow: /private')})
        c.scope=SiteScope(SITE)
        r=Results();link_checks([p],c,r)
        self.assertLessEqual(len(c.log),9)
        self.assertTrue(all(e['url'].startswith(SITE) and e['url']!=SITE+'private' for e in c.log))

    def test_policy_events_are_separate_and_product_policy_difference_is_reviewed(self):
        a=page(document(body='<p>Orders ship within 2 working days.</p><p>Returns within 7 days of delivery.</p><p>Refunds arrive within 5 days.</p>',markup=product()),SITE+'products/chair')
        b=page(document(body='<p>Orders dispatch within 4 working days.</p>'),SITE+'shipping')
        claims=extract_policy_claims(a,'Shop')+extract_policy_claims(b,'Shop')
        self.assertEqual({c['attribute'] for c in claims},{'dispatch_window','return_window','refund_window'})
        r=Results();compare_site_claims(claims,r)
        self.assertFalse(r.findings)
        self.assertTrue(any(x['check_id']=='claims.product_policy_scope' for x in r.reviews))

    def test_unrelated_faq_qualifier_is_not_a_context_defect(self):
        p=page(document(body='<p>Free shipping above INR 299.</p><p>This deal is only valid for phone cases.</p>'),SITE+'products/chair')
        r=Results();stress_tests([p],candidates([p],'Shop',None),'Shop',r)
        self.assertFalse(r.findings)
        self.assertFalse(any(t['status']=='fail' for t in r.fact_tests))


class BroadAuditTests(unittest.TestCase):
    def test_new_static_findings_survive_browser_termination(self):
        c=collector({SITE+'robots.txt':response(''),SITE:response(document().replace('<title>Chair</title>',''))})
        saved=[]
        with patch('auditlib.runner.render_pages',side_effect=SystemExit('terminated')):
            with self.assertRaises(SystemExit):
                audit(SITE,collector=c,checkpoint=lambda r:saved.append(r))
        self.assertTrue(any(f['check_id']=='seo.title_missing' for f in saved[-1]['findings']))

    def test_broad_sample_finds_schema_and_search_issues_without_pagination_dominating(self):
        urls=['products/chair','products/table','products/lamp','collections/furniture',
              'returns','shipping','about','contact']
        urls+=['collections/furniture?page='+str(i) for i in range(2,15)]
        routes={SITE+'robots.txt':response(''),SITE:response(document('Shop',body=''.join('<a href="/'+u+'">'+u+'</a>' for u in urls)))}
        for u in urls:
            routes[SITE+u]=response(document('Item',body='<p>Our published details and conditions.</p>'))
        c=collector(routes)
        r=audit(SITE,collector=c,browser=False)
        sampled=r['run_metadata']['pages_audited']
        self.assertEqual(len([u for u in sampled if '/products/' in u]),3)
        self.assertLess(sampled.index(SITE+'products/lamp'),sampled.index(SITE+'collections/furniture?page=2'))
        self.assertTrue(any(f['check_id']=='schema.product_missing' and '3 of 3' in f['evidence'] for f in r['findings']))
        self.assertTrue(any(f['check_id']=='seo.title_duplicate' for f in r['findings']))
        compact=owner_report(r)
        self.assertLess(len(json.dumps(compact,indent=2).splitlines()),220)

    def test_owner_report_limits_size_and_discloses_omitted_findings(self):
        r=Results()
        for i in range(20):
            r.finding('seo.issue'+str(i),SITE+str(i),'Distinct issue '+str(i),'Observed evidence','Correct the issue. Update its template.','Verify the correction.',severity='high' if i==19 else 'low')
        report={'site':SITE,'audited_at':'now','findings':r.findings,'checks':r.checks,'run_metadata':{'pages_audited':[SITE]}}
        owner=owner_report(report)
        self.assertEqual(owner['summary']['total_findings'],8)
        self.assertEqual(owner['summary']['high'],1)
        self.assertIn('12 additional',owner['note'])
        self.assertLess(len(json.dumps(owner,indent=2).splitlines()),200)


if __name__=='__main__':
    unittest.main()
