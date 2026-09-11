"""Conservative freshness checks; evidence details stay outside owner output."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from urllib.parse import urljoin, urlsplit
from .diagnostics import evidence, norm, compare_claims


def iso_date(value):
    """Accept explicit ISO calendar dates, not arbitrary numbers or inferred age."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def has_type(node, kind):
    types = node.get('@type', [])
    return kind in (types if isinstance(types, list) else [types])


def extract_product_claims(page, brand, source=None):
    """Bind prices to Product identity and Offer scope; never to nearby headings."""
    source = {'ownership': 'brand'} if source is None else source
    claims, seen = [], set()
    nodes = {n.get('@id'): n for n in page.nodes if isinstance(n.get('@id'), str)}
    for product in page.nodes:
        if not has_type(product, 'Product'):
            continue
        name = product.get('name')
        # Global identifiers permit cross-publisher comparisons; SKU alone does not.
        gtin = next((product.get(k) for k in ('gtin', 'gtin13', 'gtin14', 'gtin12', 'gtin8') if product.get(k)), None)
        product_url = product.get('url')
        if not isinstance(name, str) or not (gtin or isinstance(product_url, str)):
            continue
        identity = 'gtin:' + str(gtin) if gtin else urljoin(page.url, product_url)
        identity += '|sku:' + str(product.get('sku', ''))
        identity += '|variant:' + json.dumps({k: product[k] for k in ('size', 'color', 'material', 'pattern') if k in product}, sort_keys=True)
        offers = product.get('offers', [])
        for offer in offers if isinstance(offers, list) else [offers]:
            if not isinstance(offer, dict):
                continue
            offer = nodes.get(offer.get('@id'), offer) if isinstance(offer.get('@id'), str) else offer
            if not has_type(offer, 'Offer'):
                continue
            try:
                price = Decimal(str(offer.get('price')))
                if not price.is_finite() or price < 0:
                    continue
            except InvalidOperation:
                continue
            currency = offer.get('priceCurrency')
            if not isinstance(currency, str) or not re.fullmatch('[A-Z]{3}', currency):
                continue
            # Preserve all supplied offer scope so omitted qualifiers cannot be discarded.
            scope = {k: v for k, v in offer.items() if k not in ('@type', '@id', 'price', 'url')}
            key = (identity, str(price.normalize()), json.dumps(scope, sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            claims.append({'entity': identity, 'attribute': 'price', 'value': format(price.normalize(), 'f'),
                'unit': currency, 'billing_period': None,
                'region': json.dumps(offer['eligibleRegion'], sort_keys=True) if offer.get('eligibleRegion') else None,
                'effective_date': offer.get('validFrom') if iso_date(offer.get('validFrom')) else None,
                'exceptions': json.dumps(scope, sort_keys=True), 'source_url': page.url,
                'evidence_span': name + ': ' + json.dumps(offer, ensure_ascii=False, sort_keys=True),
                'observed_at': page.observed_at, 'source_group': source.get('group'),
                'ownership': source.get('ownership', 'unknown'),
                'content_fingerprint': hashlib.sha256(norm(page.main_text).encode()).hexdigest()})
    return claims


def check_freshness(page, results):
    """Report expired published offer metadata, without claiming a sale is active."""
    observed = iso_date(page.observed_at[:10])
    checked = 0
    expired = []
    for claim in extract_product_claims(page, ''):
        scope = json.loads(claim['exceptions'])
        expiry = iso_date(scope.get('priceValidUntil'))
        if not expiry or not observed:
            continue
        checked += 1
        if expiry < observed:
            expired.append(claim)
    if expired:
        items = [evidence(page.url, c['evidence_span'], 'raw_html', observed_at=page.observed_at) for c in expired]
        dates = sorted({json.loads(c['exceptions'])['priceValidUntil'] for c in expired})
        results.finding('freshness.expired_offer', page.url,
            'Published product prices have expired validity dates',
            f"{len(expired)} product offer(s) on {page.url} have priceValidUntil before the observation date {observed}; earliest expiry: {dates[0]}.",
            'Verify the current prices and update or remove expired offer markup. Use a new expiry only when the offer really has been extended.',
            'Re-fetch the page and verify each offer against the current price and actual validity period.',
            severity='medium', items=items)
    results.check('freshness.offer_dates', page.url, 'fail' if expired else 'pass' if checked else 'unknown',
        f'Checked {checked} explicitly dated product offers; no age threshold or missing-date penalty. Published metadata does not prove a sale is currently available.')
    results.check('freshness.scope', page.url, 'unknown',
        'Automatic checks cover identifiable structured product offers. Undated prose, policy changes and JavaScript-only claims require additional evidence; absence of a finding does not verify them.')



def compare_product_claims(claims, results):
    """Retain conservative scope/ownership rules and make disagreement actionable."""
    start = len(results.findings)
    compare_claims(claims, results)
    for finding in results.findings[start:]:
        finding['title'] = 'Product prices disagree across sampled sources'
        matched = [next(c for c in claims if c['source_url'] == item['source_url'] and c['evidence_span'] == item['quote']) for item in finding['evidence_items']]
        finding['evidence'] = '; '.join(c['source_url'] + ' publishes ' + c['unit'] + ' ' + c['value'] for c in matched) + '. Product identity and supplied market, date and offer conditions match.'
        finding['suggested_action']['summary'] = 'Check which price applies to this product and market, then correct the conflicting published information or contact the external publisher.'


def check_article_dates(page, results):
    """Compare explicit modification dates only when the article is this page."""
    visible_dates = set()
    for element in page.visible.select('time[datetime]'):
        label = norm(element.parent.get_text(' ', strip=True))
        if len(label) <= 160 and re.search(r'\b(last updated|last modified|updated on|modified on)\b', label):
            text = element.get_text(' ', strip=True)
            value = iso_date(text)
            if value is None:
                for pattern in ('%B %d, %Y', '%b %d, %Y', '%d %B %Y', '%d %b %Y'):
                    try:
                        value = datetime.strptime(text, pattern).date()
                        break
                    except ValueError:
                        continue
            if value:
                visible_dates.add(value)
    if len(visible_dates) != 1:
        results.check('freshness.article_dates', page.url, 'unknown', 'No single explicitly labelled HTML modification date was available.')
        return
    canonical = page.soup.select_one('link[rel="canonical"]')
    urls = {page.url, urljoin(page.url, canonical.get('href', '')) if canonical else page.url}
    for node in page.nodes:
        if not any(has_type(node, t) for t in ('Article', 'BlogPosting', 'NewsArticle')):
            continue
        target = node.get('mainEntityOfPage') or node.get('url')
        if isinstance(target, dict):
            target = target.get('@id') or target.get('url')
        if not isinstance(target, str) or urljoin(page.url, target) not in urls:
            continue
        modified = iso_date(str(node.get('dateModified', ''))[:10])
        visible = next(iter(visible_dates))
        if modified and modified != visible:
            quote = f'{page.url}: visible last-updated date {visible}; article dateModified {modified}.'
            results.finding('freshness.article_date_mismatch', page.url,
                'The article shows conflicting update dates', quote,
                'Confirm when the article was materially updated and use that date consistently in the page and its structured data.',
                'Verify the visible last-updated date matches dateModified for this article.', severity='low')
            return


def owner_report(report):
    from .reporting import owner_report as compact
    return compact(report, 'freshness')


def prioritize_links(links):
    """Take one URL per useful page class before repeats consume the sample."""
    buckets = {}
    for url in sorted(set(links)):
        path = urlsplit(url).path.lower()
        kind = next((name for name, pattern in (
            ('product', r'/products?/'), ('pricing', r'pricing|plans'),
            ('article', r'/blogs?/|/articles?/'), ('policy', r'return|refund|shipping'),
            ('about', r'about')) if re.search(pattern, path)), 'other')
        buckets.setdefault(kind, []).append(url)
    order = ('product', 'pricing', 'article', 'policy', 'about', 'other')
    first = [buckets[k].pop(0) for k in order if buckets.get(k)]
    return first + [u for k in order for u in buckets.get(k, [])]
