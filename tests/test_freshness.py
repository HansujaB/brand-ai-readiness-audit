import json
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from auditlib.diagnostics import Page, Results
from auditlib.freshness import (iso_date, extract_product_claims, check_freshness,
    check_article_dates, compare_product_claims, owner_report, prioritize_links)


def page(nodes=None, html='', url='https://shop.example/products/coat'):
    return Page({'url': url, 'observed_at': '2026-09-10T10:00:00Z',
        'body': '<main>' + html + '</main><script type="application/ld+json">' + json.dumps(nodes or []) + '</script>'})


def product(**offer):
    return {'@type': 'Product', 'name': 'Coat', 'url': 'https://shop.example/products/coat', 'sku': 'coat-red',
        'offers': {'@type': 'Offer', 'price': '999.00', 'priceCurrency': 'INR', **offer}}


class FreshnessTests(unittest.TestCase):
    def test_no_brand_price_guessing(self):
        self.assertEqual(extract_product_claims(page(html='<h1>Shop</h1><p>INR 999</p>'), 'Shop'), [])

    def test_distinct_variants_same_price_survive(self):
        a, b = product(), product()
        b['sku'] = 'coat-blue'
        claims = extract_product_claims(page([a, b]), 'Shop')
        self.assertEqual(len(claims), 2)
        self.assertNotEqual(claims[0]['entity'], claims[1]['entity'])

    def test_expired_offer_is_metadata_issue_not_live_sale_claim(self):
        results = Results()
        check_freshness(page(product(priceValidUntil='2026-09-09')), results)
        self.assertEqual(len(results.findings), 1)
        self.assertEqual(results.findings[0]['severity'], 'medium')
        self.assertIn('validity dates', results.findings[0]['title'])

    def test_no_expiry_penalty_for_absent_future_today_invalid(self):
        for value in (None, '2026-09-10', '2027-01-01', '2026-02-30', 'yesterday'):
            results = Results()
            check_freshness(page(product(priceValidUntil=value)), results)
            self.assertEqual(results.findings, [], value)

    def test_invalid_prices_and_aggregate_offers_are_not_claims(self):
        for value in ('NaN', 'Infinity', '-1', 'not a price'):
            self.assertEqual(extract_product_claims(page(product(price=value)), 'Shop'), [])
        self.assertEqual(extract_product_claims(page(product(**{'@type': 'AggregateOffer'})), 'Shop'), [])

    def test_scoped_cross_page_disagreement_and_normalization(self):
        a = extract_product_claims(page(product(eligibleRegion='IN', validFrom='2026-09-01')), 'Shop')
        b = extract_product_claims(page(product(price='1299', eligibleRegion='IN', validFrom='2026-09-01'), url='https://shop.example/offer'), 'Shop')
        results = Results()
        compare_product_claims(a+b, results)
        self.assertEqual(len(results.findings), 1)
        self.assertIn('Product prices disagree', results.findings[0]['title'])
        self.assertEqual(a[0]['value'], '999')

    def test_different_region_dates_variants_and_conditions_not_conflicts(self):
        original = product(eligibleRegion='IN', validFrom='2026-09-01')
        for change in ({'eligibleRegion':'CA'}, {'validFrom':'2025-09-01'}, {'availability':'https://schema.org/PreOrder'}):
            other = product(price='1299', eligibleRegion='IN', validFrom='2026-09-01')
            other['offers'].update(change)
            results = Results()
            compare_product_claims(extract_product_claims(page(original), 'Shop') + extract_product_claims(page(other, url='https://shop.example/other'), 'Shop'), results)
            self.assertEqual(results.findings, [])

    def test_article_dates_bound_to_own_page(self):
        node = {'@type':'Article', 'url':'https://shop.example/products/coat', 'dateModified':'2026-09-01'}
        html = '<p>Last updated <time datetime="2026-09-02">September 2, 2026</time></p>'
        results = Results()
        check_article_dates(page(node, html), results)
        self.assertEqual(len(results.findings), 1)
        node['url'] = 'https://shop.example/other'
        results = Results()
        check_article_dates(page(node, html), results)
        self.assertEqual(results.findings, [])

    def test_publication_date_not_compared_with_modification(self):
        results = Results()
        check_article_dates(page({'@type':'Article', 'url':'https://shop.example/products/coat', 'dateModified':'2026-09-01'}, '<p>Published <time datetime="2020-01-01">2020</time></p>'), results)
        self.assertEqual(results.findings, [])

    def test_compact_groups_repeated_problem_and_explains_unassessed_site(self):
        results = Results()
        check_freshness(page(product(priceValidUntil='2020-01-01')), results)
        check_freshness(page(product(priceValidUntil='2020-01-01'), url='https://shop.example/other'), results)
        report = {'site':'https://shop.example', 'audited_at':'2026-09-10T00:00:00Z', 'findings':results.findings,
            'checks':[], 'run_metadata':{'pages_audited':['a','b'], 'capabilities_used':{}}}
        compact = owner_report(report)
        self.assertEqual(compact['summary']['total_findings'], 1)
        self.assertEqual(set(compact['findings'][0]), {'id','title','severity','evidence','suggested_action','pages'})
        self.assertEqual(len(compact['findings'][0]['pages']), 2)
        self.assertEqual(set(compact['findings'][0]['suggested_action']), {'summary','priority','verification'})
        self.assertNotIn('claims', compact)
        report['findings'] = []
        report['run_metadata']['pages_audited'] = []
        compact = owner_report(report)
        self.assertIn('could not be assessed',compact['note'])
        self.assertNotIn('coverage',compact)

    def test_nested_hidden_elements_do_not_abort_page(self):
        p = page(html='<div style="display:none"><span style="color:red">Hidden</span></div><p>Visible</p>')
        self.assertNotIn('Hidden', p.main_text)
        self.assertIn('Visible', p.main_text)

    def test_representative_links_precede_repeated_products(self):
        links = prioritize_links(['https://shop.example/products/a', 'https://shop.example/products/b', 'https://shop.example/about', 'https://shop.example/returns'])
        self.assertIn('https://shop.example/returns', links[:3])
        self.assertIn('https://shop.example/about', links[:3])

    def test_undated_different_prices_are_not_contradictions(self):
        a=extract_product_claims(page(product()), 'Shop')
        b=extract_product_claims(page(product(price='199'),url='https://shop.example/other'), 'Shop')
        results=Results();compare_product_claims(a+b,results)
        self.assertFalse(results.findings)
        self.assertTrue(all(c['status']=='unknown' for c in results.comparisons))

    def test_dates_strict(self):
        for value in (None, 2026, '2026-2-01', '2026-02-30'):
            self.assertIsNone(iso_date(value))


if __name__ == '__main__':
    unittest.main()
