"""Conservative freshness checks; evidence details stay outside owner output."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
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


def extract_product_claims(page, brand):
    """Bind prices to Product identity and Offer scope; never to nearby headings."""
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
                'observed_at': page.observed_at})
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
    results.check('freshness.offer_dates', page.url, 'fail' if expired else 'pass' if checked else 'not_applicable',
        f'Checked {checked} explicitly dated product offers; no age threshold or missing-date penalty. Published metadata does not prove a sale is currently available.')
    results.check('freshness.scope', page.url, 'not_applicable',
        'Current website evidence supports published dates and cross-page consistency; historical accuracy requires a dated source on this website.')



def compare_product_claims(claims, results):
    """Retain comparable offer scope and make disagreement actionable."""
    start = len(results.findings)
    compare_claims(claims, results)
    for finding in results.findings[start:]:
        finding['title'] = 'Product prices disagree across sampled sources'
        matched = [next(c for c in claims if c['source_url'] == item['source_url'] and c['evidence_span'] == item['quote']) for item in finding['evidence_items']]
        finding['evidence'] = '; '.join(c['source_url'] + ' publishes ' + c['unit'] + ' ' + c['value'] for c in matched) + '. Product identity and supplied market, date and offer conditions match.'
        finding['suggested_action']['summary'] = 'Check which price applies to this product and market, then correct the conflicting pages on this website.'


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
        results.check('freshness.article_dates', page.url, 'not_applicable', 'No single explicitly labelled HTML modification date was available.')
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


def prioritize_links(links, seen=()):
    """Take one URL per useful page class before repeats consume the sample."""
    buckets = {}
    for url in dict.fromkeys(links):
        path = urlsplit(url).path.lower()
        kind = next((name for name, pattern in (
            ('product', r'/products?/|/p/'), ('category', r'/cat/|/category/|/collections?/|/shop(?:/|$)'),
            ('pricing', r'pricing|plans'), ('returns', r'return|refund'), ('delivery', r'shipping|delivery'),
            ('service', r'/services?/'), ('article', r'/blogs?/|/articles?/'),
            ('about', r'/about(?:/|$)'), ('support', r'/contact|/support|/help|/faq')) if re.search(pattern, path)), 'other')
        buckets.setdefault(kind, []).append(url)
    order = ('product', 'category', 'pricing', 'returns', 'delivery', 'service', 'about', 'support', 'article', 'other')
    order = sorted(order, key=lambda kind:kind in seen)
    first = [buckets[k].pop(0) for k in order if buckets.get(k)]
    return first + [u for k in order for u in buckets.get(k, [])]


POLICY_WORDS = {
    'return_window': r'\breturns?\b|refund|exchange|वापसी|retour|rückgabe|devoluci',
    'delivery_window': r'deliver|shipping|dispatch|डिलीवरी|वितरण|livraison|liefer|entrega|envío',
    'warranty_window': r'warranty|guarantee|वारंटी|garantie|garantía',
}
DURATION = re.compile(r'(\d+(?:\s*[-–]\s*\d+)?)\s*(business\s+days?|working\s+days?|days?|weeks?|months?|years?|दिन|सप्ताह|महीने|साल|jours?|semaines?|mois|ans?|tage[ns]?|wochen|monate[ns]?|jahre[ns]?|días?|semanas?|meses|años?)\b', re.I)


def extract_policy_claims(page, brand):
    """Extract quoted duration claims; retain sentence conditions for comparisons."""
    claims, seen = [], set()
    scope = getattr(page, 'audit_scope', {})
    product = next((n for n in page.nodes if has_type(n, 'Product') and n.get('name')), None)
    entity = ('product:' + str(product.get('url') or product.get('sku') or product['name'])) if product else 'site:' + urlsplit(page.url).hostname
    for block in page.blocks:
        if block.get('tag', '') in ('h1','h2','h3'):
            continue
        for sentence in re.split(r'(?<=[.!?।])\s+', block['text']):
            matches = list(DURATION.finditer(sentence))
            if len(matches) != 1:
                continue
            kinds = [k for k, pattern in POLICY_WORDS.items() if re.search(pattern, sentence, re.I)]
            if len(kinds) != 1:
                continue
            match = matches[0]
            signature = norm(sentence[:match.start()] + '{duration}' + sentence[match.end():]).rstrip('.।')
            value, unit = re.sub(r'\s+', '', match[1]).replace('–','-'), norm(match[2])
            unit = re.sub(r's$', '', unit)
            key = (kinds[0], signature, value, unit)
            if key in seen:
                continue
            seen.add(key)
            historical = bool(re.search(r'\b(previously|formerly|used to|until 20\d\d|in 20\d\d)\b', sentence, re.I))
            claims.append({'entity': entity, 'attribute': kinds[0], 'value': value, 'unit': unit,
                'region': scope.get('country'), 'effective_date': None, 'billing_period': None,
                'exceptions': signature, 'source_url': page.url, 'evidence_span': sentence,
                'observed_at': page.observed_at, 'historical': historical, 'representation': 'raw_html',
                'locator': block['locator'], 'context_label': block['heading']})
    return claims


def compare_site_claims(claims, results):
    prices = [c for c in claims if c['attribute'] == 'price']
    compare_product_claims(prices, results)
    for comparison in results.comparisons:
        if comparison['status'] == 'unknown':
            results.review('claims.scope', comparison['evidence_items'][0]['source_url'],
                'Do these product offers describe the same active price and conditions?',
                comparison['reason'], comparison['evidence_items'])
    policies = [c for c in claims if c['attribute'] in POLICY_WORDS]
    for i, left in enumerate(policies):
        for right in policies[i+1:]:
            if left['source_url'] == right['source_url'] or left['entity'] != right['entity'] or left['attribute'] != right['attribute']:
                continue
            if left.get('historical') or right.get('historical'):
                status = 'historical_difference'
            elif left['region'] != right['region']:
                status = 'regional_difference'
            elif left['exceptions'] == right['exceptions'] and left['unit'] == right['unit'] and norm(left['context_label']) == norm(right['context_label']):
                status = 'consistent' if left['value'] == right['value'] else 'contradiction'
            else:
                status = 'unknown'
            items = [evidence(c['source_url'], c['evidence_span'], observed_at=c['observed_at'], locator=c['locator']) for c in (left,right)]
            results.comparisons.append({'entity': left['entity'], 'attribute': left['attribute'], 'status': status,
                'reason': 'Compared quoted policy statements in one website locale; sentence conditions and units are retained.', 'evidence_items': items})
            if status == 'contradiction':
                results.finding('claims.policy_conflict', left['source_url'],
                    'The website publishes conflicting ' + left['attribute'].replace('_window','') + ' durations',
                    '; '.join(c['source_url'] + ': ' + c['evidence_span'] for c in (left,right)),
                    'Confirm the applicable duration and update both quoted statements, including any product or service exceptions.',
                    'Repeat the same visitor question on both cited pages in the selected country and language.',
                    entity=left['entity'], root_cause=left['attribute'] + ':' + left['exceptions'], severity='medium',
                    confidence='medium', reason='Same website, subject, wording, conditions and units; different published values.', items=items)
            elif status == 'unknown' and left['value'] != right['value']:
                results.review('claims.policy_scope', left['source_url'], 'Which ' + left['attribute'].replace('_',' ') + ' applies?',
                    'Different durations appear with different wording or conditions; a contradiction is not established.', items)
