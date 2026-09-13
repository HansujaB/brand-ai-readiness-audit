"""Page-specific structured-data coverage, using only collected representations."""
import json
import re
from urllib.parse import urljoin, urldefrag

from .crawl import amount
from .diagnostics import Page, evidence, norm


def values(value):
    return value if isinstance(value, list) else [value] if value is not None else []


def types(node):
    return {str(t).rstrip('/').rsplit('/', 1)[-1].rsplit(':', 1)[-1] for t in values(node.get('@type'))}


def graph(page):
    nodes = list(page.nodes)
    for sample in page.rendered.values():
        if sample.get('metadata_html'):
            nodes.extend(Page({**page.response, 'body':sample['metadata_html'].encode('utf-8')}).nodes)
    nodes = list({json.dumps(n, sort_keys=True):n for n in nodes}.values())
    identifiers = {}
    for node in nodes:
        if isinstance(node.get('@id'), str):
            key = urljoin(page.url, node['@id'])
            identifiers[key] = {**identifiers.get(key, {}), **node}

    def resolve(value):
        if isinstance(value, dict):
            key = value.get('@id')
            return {**identifiers.get(urljoin(page.url, key), {}), **value} if isinstance(key, str) else value
        return {}

    return [resolve(n) for n in nodes], resolve


def product_nodes(page, nodes, resolve):
    candidates = [n for n in nodes if 'Product' in types(n)]
    heading = page.visible.find('h1')
    name = norm(heading.get_text(' ', strip=True)) if heading else ''
    matched = [n for n in candidates if name and norm(n.get('name', '')) == name]
    if matched:
        return matched
    own_urls = {urldefrag(page.url)[0].split('?')[0]}
    for link in page.soup.select('link[rel="canonical"][href]'):
        own_urls.add(urljoin(page.base_url, link['href']).split('?')[0].split('#')[0])
    matched = [n for n in candidates if any(isinstance(n.get(k), str) and
        urljoin(page.url, n[k]).split('?')[0].split('#')[0] in own_urls for k in ('url', '@id'))]
    if matched:
        return matched
    # ProductGroup variants can inherit shared fields from the group.
    groups = [n for n in nodes if 'ProductGroup' in types(n)]
    if len(groups) == 1:
        group = groups[0]
        variants = [resolve(n) for n in values(group.get('hasVariant'))]
        return [{**{k:v for k,v in group.items() if k not in ('hasVariant','@type','@id')}, **n}
                for n in variants if 'Product' in types(n)]
    return candidates if len(candidates) == 1 else []


def offer_errors(offer, resolve):
    if not types(offer) & {'Offer', 'AggregateOffer'}:
        return ['offers.@type (Offer or AggregateOffer)']
    if 'AggregateOffer' in types(offer):
        errors = ['offers.lowPrice'] if amount(offer.get('lowPrice')) is None else []
        if not re.fullmatch(r'[A-Z]{3}', str(offer.get('priceCurrency', ''))):
            errors.append('offers.priceCurrency')
        if 'highPrice' in offer and (amount(offer['highPrice']) is None or
                amount(offer.get('lowPrice')) is not None and amount(offer['highPrice']) < amount(offer['lowPrice'])):
            errors.append('offers.highPrice (valid range)')
        return errors
    prices = [offer] if 'price' in offer else [resolve(p) for p in values(offer.get('priceSpecification'))]
    prices = [p for p in prices if not p.get('priceType') and not p.get('validForMemberTier')]
    if not any(amount(p.get('price')) is not None for p in prices):
        return ['offers.price or active priceSpecification.price']
    return []


def coverage_checks(pages, results):
    product_pages = [p for p in pages if p.purpose == 'product' and p.main_text.strip()]
    missing = []
    for page in pages:
        nodes, resolve = graph(page)
        if page not in product_pages:
            if page.purpose == 'article' and page.visible.find('article') and not any(
                    types(n) & {'Article','BlogPosting','NewsArticle'} for n in nodes):
                results.suggest('schema.article', page.url,
                    'The page publishes an article, but collected markup has no Article or BlogPosting entity.',
                    'Describe this article with Article or BlogPosting markup using its published headline, author and dates. Keep those values consistent with the article text.',
                    'Validate the article markup and compare each populated field with the page.', priority='medium')
            continue
        products = product_nodes(page, nodes, resolve)
        if not products:
            if page.invalid_jsonld or page.markup_limits or any(types(n) & {'Product','ProductGroup'} for n in nodes):
                results.review('schema.product_scope', page.url, 'Does the markup describe this product?',
                    'Malformed, referenced or multiple product entities prevent a reliable page-product match.',
                    [evidence(page.url, json.dumps(nodes, ensure_ascii=False)[:1200], 'structured_data')])
            else:
                missing.append(page)
            continue
        results.check('schema.product_coverage', page.url, 'pass', 'Product markup identified; field validation follows.')
        if page.markup_limits:
            results.review('schema.product_scope', page.url, 'Are the product fields complete after resolving markup references?',
                'Unsupported markup relationships prevent reliable missing-property checks.',
                [evidence(page.url, '; '.join(page.markup_limits), 'structured_data')])
            continue
        for product in products:
            errors = []
            if not isinstance(product.get('name'), str) or not product['name'].strip():
                errors.append('name')
            offers = [resolve(o) for o in values(product.get('offers'))]
            if not offers and not product.get('review') and not product.get('aggregateRating'):
                errors.append('offers, review or aggregateRating')
            for offer in offers:
                # References which the supported parser cannot resolve need review.
                if offer.get('@id') and not offer.get('@type'):
                    results.review('schema.offer_reference', page.url, 'Where is this offer defined?',
                        'The offer reference was not resolved in the collected markup.',
                        [evidence(page.url, json.dumps(offer), 'structured_data')])
                    continue
                errors.extend(offer_errors(offer, resolve))
            errors = sorted(set(errors))
            if errors:
                results.finding('schema.product_fields', page.url, 'Product markup has missing or invalid search fields',
                    (str(product.get('name') or 'Product') + ': missing or invalid ' + ', '.join(errors) + '.'),
                    'Complete the identified Product and Offer fields in the product template using the published product details. Use valid prices and keep variants and conditional offers separate.',
                    'Run the Product rich-result validator and compare the repaired fields with the same product and offer.',
                    root_cause='product-fields:' + ','.join(errors),
                    items=[evidence(page.url, json.dumps(product, ensure_ascii=False)[:1800], 'structured_data')])
            elif offers:
                incomplete = []
                for offer in offers:
                    prices = [offer] if 'price' in offer else [resolve(p) for p in values(offer.get('priceSpecification'))]
                    if 'Offer' in types(offer) and not any(re.fullmatch(r'[A-Z]{3}', str(p.get('priceCurrency', ''))) for p in prices):
                        incomplete.append('currency')
                if not product.get('image'):
                    incomplete.append('product image')
                if incomplete:
                    results.suggest('schema.merchant_details', page.url,
                        str(product.get('name', 'Product')) + ': collected product/offer data lacks ' + ', '.join(sorted(set(incomplete))) + '.',
                        'Complete the product image and applicable offer currency using the published product details. Check the requirements for merchant listings separately from basic product snippets.',
                        'Validate merchant-listing fields for the same purchasable product; do not add invented values.', priority='medium')
    if missing:
        quote = (f'{len(missing)} of {len(product_pages)} sampled product pages have no Product markup in the collected HTML'
                 ' or available rendered metadata; other schema types do not describe the product.')
        results.finding('schema.product_missing', missing[0].url, 'Product pages lack product-specific structured data', quote,
            'Add Product markup to the affected product template, including the product name and the applicable offer or review details. Use the published price, currency and availability for each offer and preserve variant differences.',
            'Validate each affected product page and confirm that the markup matches its displayed product and offer.',
            severity='medium', items=[evidence(p.url, quote, 'collected_markup') for p in missing],
            reason='Confirmed omission in collected representations; complete JavaScript rendering and search visibility are not assumed.')
