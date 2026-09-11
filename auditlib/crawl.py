"""Scoped index directives, canonical observations and identity-bound offer checks.
See docs/crawl-orchestrator-research.md for sources and deliberate limits.
"""
import hashlib
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin
from .collection import normalize
from .diagnostics import evidence, norm

DIRECTIVES = {'index','noindex','follow','nofollow','none','all','nosnippet','max-snippet','max-image-preview','max-video-preview','noarchive','notranslate','noimageindex','unavailable_after','indexifembedded'}


def directives(value, default='*'):
    scope = default.lower()
    for part in str(value).split(','):
        part = part.strip().lower()
        if not part:
            continue
        key, colon, rest = part.partition(':')
        if colon and key.strip() not in DIRECTIVES:
            scope = key.strip()
            part = rest.strip()
        key, colon, rest = part.partition(':')
        # Values such as max-image-preview:none must never become bare `none`.
        if key.strip() in DIRECTIVES:
            yield scope, key.strip(), rest.strip() if colon else ''


def report_directives(url, records, results, representation):
    restrictions = {}
    for scope, key, value in records:
        if key in ('noindex','none','nosnippet','nofollow','noimageindex') or key == 'max-snippet':
            restrictions.setdefault(scope, []).append(key + (':' + value if value else ''))
    for scope, values in restrictions.items():
        quote = f"{representation}: {scope}: {', '.join(values)}"
        if scope not in ('*','googlebot','googlebot-news','bingbot'):
            results.check('access.scoped_directive', url, 'unknown', quote + '; this crawler token is outside the verified directive-support set.', [evidence(url, quote, representation)])
            continue
        if any(v in ('noindex','none') for v in values):
            results.finding('access.noindex', url, 'Index exclusion observed' + (' for ' + scope if scope != '*' else ''), quote,
                'Confirm that this page should appear in the affected search engine before changing its index directive.',
                'Inspect response headers and HTML directives for that crawler.', entity=scope, root_cause='noindex:' + scope,
                items=[evidence(url, quote, representation)])
        preview = [v for v in values if v == 'nosnippet' or v.startswith('max-snippet:')]
        if preview:
            results.check('access.preview', url, 'not_applicable', quote + '; deliberate snippet controls may limit search previews; intent is not inferred.', [evidence(url, quote, representation)])
    if not any(key in ('noindex','none') for _, key, _ in records):
        results.check('access.noindex', url, 'pass', 'No recognized index exclusion in ' + representation + '; indexing is not guaranteed.')


def header_checks(url, headers, results):
    records = []
    for key, value in headers.items():
        if key.lower() == 'x-robots-tag':
            for entry in value if isinstance(value, list) else [value]:
                records.extend(directives(entry))
    report_directives(url, records, results, 'http_headers')


def metadata_checks(page, results, representation='raw_html'):
    records = []
    for key, value in page.response.get('headers', {}).items():
        if key.lower() == 'x-robots-tag':
            for entry in value if isinstance(value, list) else [value]:
                records.extend(directives(entry))
    for tag in page.soup.find_all('meta'):
        name = tag.get('name', '').lower()
        if name in ('robots','googlebot','bingbot','googlebot-news'):
            records.extend(directives(tag.get('content', ''), '*' if name == 'robots' else name))
    report_directives(page.url, records, results, representation)
    excluded = page.soup.select('[data-nosnippet]')
    if excluded:
        results.check('access.preview_sections', page.url, 'not_applicable', str(len(excluded)) + ' sections declare data-nosnippet; snippet policy is not a page defect.')
    targets = []
    for link in page.soup.find_all('link', href=True):
        if 'canonical' in [str(x).lower() for x in link.get('rel', [])]:
            try:
                targets.append(normalize(urljoin(page.base_url, link['href'])))
            except ValueError:
                results.finding('access.canonical_invalid', page.url, 'Canonical target is not a usable public web URL', link['href'],
                    'Correct the canonical URL after confirming the preferred page.', 'Resolve the canonical URL against the document base.', severity='low')
    if len(set(targets)) > 1:
        results.finding('access.canonical_conflict', page.url, 'Page declares conflicting canonical targets', ', '.join(sorted(set(targets))),
            'Declare one preferred canonical target for this page.', 'Inspect raw and rendered canonical links.', severity='medium')
    else:
        results.check('access.canonical', page.url, 'pass' if targets else 'not_applicable',
            'Declared canonical: ' + targets[0] + '; target availability and selection are not established.' if targets else 'No HTML canonical declared; absence alone is not a defect.')


def amount(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number >= 0 else None
    except InvalidOperation:
        return None


def schema_checks(page, results):
    for quote, error in page.invalid_jsonld:
        results.finding('schema.invalid_jsonld', page.url, 'Structured data contains invalid JSON', 'A JSON-LD block could not be parsed: ' + error,
            'Repair the JSON syntax in the identified block.', 'Parse all JSON-LD blocks and run the relevant rich-result validator.',
            root_cause=hashlib.sha256(quote.encode()).hexdigest(), items=[evidence(page.url, quote, 'structured_data')])
    results.check('schema.formats', page.url, 'pass' if page.formats else 'not_applicable',
        'Observed formats: ' + ', '.join(sorted(set(page.formats))) if page.formats else 'No recognized markup; absence alone is not a defect.')
    for limitation in page.markup_limits:
        results.check('schema.scope', page.url, 'unknown', limitation)
    invalid = []
    for node in page.nodes:
        if 'price' in node and amount(node['price']) is None:
            invalid.append(str(node['price'])[:80])
    if invalid:
        results.finding('schema.invalid_price', page.url, 'Structured offer price is not a valid number', 'Invalid offer price values: ' + ', '.join(sorted(set(invalid))),
            'Use a non-negative numeric price and a separate ISO currency code for the applicable offer.', 'Validate the offer against visible product details.', severity='medium')
    if not page.formats and page.purpose in ('product','pricing','article'):
        results.suggest('schema.contextual', page.url, 'Page purpose: ' + page.purpose, 'Consider applicable structured data for confirmed visible facts.', 'Use the search feature validator; markup does not guarantee visibility.')
    # Compare only a named Product with its own single Offer and explicitly marked visible price.
    from .freshness import has_type
    products = [n for n in page.nodes if has_type(n, 'Product')]
    if len(products) != 1:
        return
    product = products[0]
    name = product.get('name')
    heading = page.visible.find('h1')
    offers = product.get('offers', [])
    offers = offers if isinstance(offers, list) else [offers]
    price_nodes = page.visible.select('[itemprop="price"],[data-product-price]')
    if not isinstance(name, str) or not heading or norm(name) != norm(heading.get_text(' ', strip=True)) or len(offers) != 1 or len(price_nodes) != 1 or not isinstance(offers[0], dict):
        if any('price' in n for n in page.nodes):
            results.check('schema.visible_price', page.url, 'unknown', 'Visible price cannot be bound to one named product and offer; shipping, variants and conditions are not compared.')
        return
    offer, element = offers[0], price_nodes[0]
    if any(k in offer for k in ('priceSpecification','eligibleRegion','eligibleQuantity','validFrom','availabilityStarts')) or product.get('isVariantOf'):
        results.check('schema.visible_price', page.url, 'unknown', 'Offer has variant or conditional scope requiring explicit visible scope resolution.')
        return
    container = element.find_parent(attrs={'itemscope':True})
    if container:
        declared = container.get('itemtype','').rsplit('/',1)[-1]
        if declared not in ('Product','Offer'):
            return
    text = element.get_text(' ', strip=True)
    match = re.fullmatch(r'\s*(USD|EUR|GBP|INR|€|£|₹)?\s*([0-9]+(?:\.[0-9]+)?)\s*(USD|EUR|GBP|INR)?\s*', text, re.I)
    if not match:
        results.check('schema.visible_price', page.url, 'unknown', 'Visible price does not state an unambiguous currency and amount.')
        return
    currency = (match[1] or match[3] or '').upper()
    currency = {'€':'EUR','£':'GBP','₹':'INR'}.get(currency, currency)
    value = amount(offer.get('price'))
    if not currency or value is None or not isinstance(offer.get('priceCurrency'), str):
        return
    if amount(match[2]) != value or currency != offer['priceCurrency'].upper():
        quote = f"{name}: visible price {currency} {match[2]}; structured offer {offer['priceCurrency']} {offer['price']}."
        results.finding('schema.visible_price', page.url, 'Product price and structured offer disagree', quote,
            'Align the visible and structured price for this same product, currency and offer.', 'Check the named product and active offer in both representations.',
            entity=name, confidence='medium', reason='Explicit product heading and marked price matched; confirm the active offer before changing it.')
    else:
        results.check('schema.visible_price', page.url, 'pass', 'Explicit named-product price and currency match the single structured offer.')
