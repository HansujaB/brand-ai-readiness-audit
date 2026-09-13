"""Content evidence and conservative, deterministic diagnostic checks."""
import io
import json
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from .collection import utcnow, CRAWLERS

MONEY = re.compile(r'(?:₹|\$|€|£|INR\s*|USD\s*|EUR\s*|GBP\s*)\s*\d[\d,]*(?:\.\d{1,2})?', re.I)
REGION = re.compile(r'\b(?:India|United States|United Kingdom|Europe|Canada|Australia)\b', re.I)
PERIOD = re.compile(r'(?:/|per\s+)(month|year|week|day|user|seat)|\b(monthly|annually|yearly)\b', re.I)


def clean(value):
    return re.sub(r'\s+', ' ', value).strip()


def norm(value):
    return clean(str(value)).casefold()


def evidence(url, text, representation='raw_html', locator=None, observed_at=None):
    return {'source_url': url, 'representation': representation, 'quote': text,
            'locator': locator, 'observed_at': observed_at or utcnow()}


class Results:
    def __init__(self):
        self.findings, self.checks, self.suggestions = [], [], []
        self.fact_tests, self.claims, self.comparisons, self.journeys, self.rewrites = [], [], [], [], []
        self.reviews = []

    def check(self, check_id, url, status, reason, items=None):
        self.checks.append({'check_id': check_id, 'resource': url, 'status': status,
                            'reason': reason, 'evidence_items': items or []})

    def finding(self, check_id, url, title, quote, action, verification, severity='medium',
                category='discoverability', entity='', root_cause=None, confidence='high', reason='Directly observed in collected evidence.', items=None):
        items = items or [evidence(url, quote)]
        self.findings.append({'check_id': check_id, 'entity': entity, 'resource': url,
            'root_cause': root_cause or check_id, 'title': title, 'severity': severity,
            'category': category, 'affected_urls': list(dict.fromkeys(i['source_url'] for i in items)),
            'confidence': confidence, 'confidence_reason': reason, 'evidence': quote,
            'evidence_items': items, 'suggested_action': {'summary': action, 'priority': severity if severity != 'critical' else 'high',
                'effort': 'medium', 'verification': verification}})
        self.check(check_id, url, 'fail', title, items)

    def suggest(self, check_id, url, quote, action, verification, priority='low', effort='low', items=None):
        self.suggestions.append({'check_id': check_id, 'resource': url,
            'evidence_items': items or [evidence(url, quote)], 'suggested_action': {'summary': action,
                'priority': priority, 'effort': effort, 'verification': verification},
            'limitation': 'An evidence improvement hypothesis; no commercial assistant visibility gain is established.'})

    def review(self, check_id, url, question, reason, items=None, next_step=None):
        self.reviews.append({'check_id': check_id, 'source_url': url, 'question': question,
            'reason': reason, 'evidence_items': items or [],
            'next_step': next_step or 'Inspect the cited page and its linked policy or specification in the selected locale; resolve scope before recommending a correction.'})


def json_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from json_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from json_nodes(child)


class Page:
    def __init__(self, response):
        self.url, self.observed_at = response['url'], response.get('observed_at', utcnow())
        self.response = response
        self.soup = BeautifulSoup(response['body'], 'html.parser')
        self.nodes, self.invalid_jsonld = [], []
        for script in self.soup.select('script[type="application/ld+json"]'):
            try:
                self.nodes.extend(json_nodes(json.loads(script.get_text())))
            except (ValueError, TypeError) as exc:
                self.invalid_jsonld.append((script.get_text()[:500], str(exc)))
        from .markup import scoped_nodes
        self.formats = ['jsonld'] if self.nodes else []
        self.markup_limits = []
        for kind, nodes, limits in scoped_nodes(self.soup):
            self.nodes.extend(nodes)
            self.formats.append(kind)
            self.markup_limits.extend(limits)
        self.lang = (self.soup.html.get('lang', 'und') if self.soup.html else 'und').lower()
        base = self.soup.find('base', href=True)
        self.base_url = urljoin(self.url, base['href']) if base else self.url
        self.links = [{'url': urljoin(self.base_url, a['href']), 'name': a.get('aria-label') or a.get_text(' ', strip=True),
                       'in_main': bool(a.find_parent(['main','article']) or a.find_parent(attrs={'role':'main'}))}
                      for a in self.soup.select('a[href]')]
        visible = BeautifulSoup(str(self.soup), 'html.parser')
        for element in visible.select('script,style,template,[hidden],[aria-hidden="true"]'):
            element.decompose()
        for element in list(visible.select('[style]')):
            if element.attrs is None:
                continue  # A hidden ancestor may already have decomposed this child.
            if re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', element.get('style', ''), re.I):
                element.decompose()
        self.visible = visible
        self.text = visible.get_text(' ', strip=True)
        main = visible.select_one('main,article,[role="main"]') or visible.body or visible
        self.main_text = main.get_text(' ', strip=True)
        self.accessible_text = self.main_text + ' ' + ' '.join(e.get('alt', '') + ' ' + e.get('aria-label', '') for e in main.select('[alt],[aria-label]'))
        self.blocks = []
        for index, element in enumerate(main.select('p,li,tr,h1,h2,h3,dt,dd')):
            text = element.get_text(' ', strip=True)
            if not text:
                continue
            scope = element.find_parent(['section', 'article', 'li']) or main
            heading = element if re.match(r'^h[1-6]$', element.name) else element.find_previous(re.compile(r'^h[1-6]$'))
            table = element.find_parent('table')
            headers = ' | '.join(h.get_text(' ', strip=True) for h in table.select('th')) if table else ''
            self.blocks.append({'text': text, 'heading': heading.get_text(' ', strip=True) if heading else '',
                                'headers': headers, 'locator': element.name + ':' + str(index),
                                'section_text': scope.get_text(' ', strip=True), 'section_is_main': scope is main,
                                'tag': element.name})
        # Pricing cards often use div/span without paragraphs. Retain the closest compact container.
        for textnode in main.find_all(string=MONEY):
            element = textnode.parent
            container = element.find_parent(['section', 'article', 'li']) or element.parent
            text = container.get_text(' ', strip=True) if container else str(textnode)
            if len(text) < 1200 and not any(text == b['text'] for b in self.blocks):
                heading = container.find(re.compile(r'^h[1-6]$')) if container else None
                self.blocks.append({'text': text, 'heading': heading.get_text(' ', strip=True) if heading else '', 'headers': '', 'locator': 'price-container'})
        from .engagement import page_purpose
        self.purpose = page_purpose(self)
        self.rendered = {}


def crawl_checks(page, results, collector):
    url = page.url
    policy = collector.policy(url)
    for agent, role in CRAWLERS.items():
        allowed, rule, _ = policy.decision(agent, url)
        item = evidence(url, rule, 'robots_txt', agent)
        results.check('access.crawler.' + agent, url, 'unknown' if allowed is None else 'pass' if allowed else 'not_applicable' if role != 'search' else 'fail',
                      role + ': ' + rule + ('; permission choice, not a search visibility defect' if role != 'search' else ''), [item])
        if allowed is False and role == 'search':
            results.finding('access.search_exclusion', url, 'Search crawler excluded: ' + agent, rule,
                            'Confirm the intended search policy; allow this informational path for ' + agent + ' if it should be discoverable.',
                            'Re-run the robots decision for this URL and crawler. Preserve training exclusions.',
                            entity=agent, root_cause='robots:' + agent, items=[item])
    from .crawl import metadata_checks, schema_checks
    metadata_checks(page, results)
    schema_checks(page, results)


def candidates(pages, brand, supplied):
    if supplied:
        return [({'question': x, 'terms': []} if isinstance(x, str) else x) for x in supplied][:5]
    found = []
    for page in pages:
        for block in page.blocks:
            price = MONEY.search(block['text'])
            policy = re.search(r'\b(?:return|refund|warranty|deliver|shipping)\w*\b.{0,90}?\b\d+\s*(?:business\s+)?(?:days?|weeks?|months?|years?)\b', block['text'], re.I)
            detail = re.search(r'\b(?:dimensions?|compatible with|available in|service area|contact us|material|capacity)\b[^.!?]{3,100}', block['text'], re.I)
            match = price or policy or detail
            if not match or not block['heading']:
                continue
            if any(f['terms'] == [match[0], block['heading']] and f['source_url'] == page.url for f in found):
                continue
            found.append({'question': 'What is the ' + ('price and commitment' if price else 'policy and exceptions' if policy else 'specification or service scope') + ' for ' + block['heading'] + '?',
                'terms': [match[0], block['heading']], 'source_url': page.url, 'locator': block['locator'], 'inferred': True,
                'context': discover_context(page, block)})
    # Round-robin across pages so a price-heavy landing page cannot consume all questions.
    buckets = {}
    for fact in found:
        buckets.setdefault(fact['source_url'], []).append(fact)
    selected = []
    while any(buckets.values()) and len(selected) < 5:
        for bucket in buckets.values():
            if bucket and len(selected) < 5:
                selected.append(bucket.pop(0))
    return selected


def discover_context(page, block):
    """Find section qualifications or explicit single-offer terms, excluding footers."""
    contexts = []
    price_subjects = {b['heading'] for b in page.blocks if MONEY.search(b['text'])}
    for other in page.blocks:
        if other['locator'] == block['locator'] or other.get('tag') in ('h1','h2','h3'):
            continue
        same_section = (other.get('section_text') and other.get('section_text') == block.get('section_text')
                        and (not block.get('section_is_main') or other['heading'] == block['heading']))
        conditions_section = len(price_subjects) == 1 and re.search(r'condition|billing|eligibility|terms|exception', other['heading'], re.I)
        qualification = re.search(r'billed\s+(?:annually|monthly)|\bonly\b|exclud|except|subject to|minimum|non.returnable|final sale', other['text'], re.I)
        if (same_section or conditions_section) and qualification and len(other['text']) < 500:
            contexts.append(other['text'])
    contexts = list(dict.fromkeys(contexts))
    return {('exceptions' if i == 0 else 'condition_' + str(i+1)): text for i,text in enumerate(contexts)}


def stress_tests(pages, facts, brand, results):
    for fact in facts:
        question = fact['question']
        terms = [norm(t) for t in fact.get('terms', []) if t]
        matches = []
        for page in pages:
            if fact.get('source_url') and fact['source_url'].rstrip('/') != page.url.rstrip('/'):
                continue
            for block in page.blocks:
                excerpt = clean(' '.join([block['heading'], block['headers'], block['text']]))
                if terms and all(t in norm(excerpt) for t in terms):
                    matches.append((page, block, excerpt))
        if not matches:
            rendered_matches = [(p, name, r) for p in pages for name, r in p.rendered.items()
                                if (not fact.get('source_url') or fact['source_url'].rstrip('/') == p.url.rstrip('/'))
                                and terms and all(t in norm(r['text']) for t in terms)]
            results.fact_tests.append({'question': question, 'status': 'unknown', 'reason': 'No supporting raw section matched the supplied terms; absence does not prove media locking.',
                                      'rendered_matches': [name for _, name, _ in rendered_matches], 'evidence_items': []})
            for p, name, rendered in rendered_matches[:1]:
                if not rendered.get('content_reliable', rendered.get('reliable', False)):
                    continue
                if all(t in norm(p.accessible_text) for t in terms):
                    continue
                span = next((b for b in rendered['blocks'] if all(t in norm(b) for t in terms)), rendered['text'][:1500])
                is_price = any(MONEY.search(t) for t in terms)
                results.finding('render.essential_fact' if is_price else 'render.target_fact', p.url, 'Requested fact is absent from raw accessible content', span,
                                'Expose this fact and its context in accessible server-rendered content.',
                                'Re-run the supplied fact question against raw and rendered representations.', severity='medium', confidence='medium', reason='Observed representation difference; this does not establish exclusion from JavaScript-capable search engines.', entity='price' if is_price else question, root_cause='rendered-price' if is_price else 'rendered-target',
                                items=[evidence(p.url, span, 'rendered_' + name), evidence(p.url, p.accessible_text[:1200], 'raw_accessible_text')])
            continue
        page, block, excerpt = max(matches, key=lambda m: (sum(norm(v) in norm(m[2]) for v in fact.get('context', {}).values()), -len(m[2])))
        context = {**discover_context(page, block), **fact.get('context', {})}
        if block['heading']:
            context.setdefault('entity', block['heading'])
        amount = MONEY.search(block['text'])
        period = PERIOD.search(block['text'])
        region = REGION.search(block['text'])
        effective = re.search(r'effective\s+(20\d\d-\d\d-\d\d)', block['text'], re.I)
        if amount:
            context.setdefault('value', amount[0])
            context.setdefault('unit', re.sub(r'[\d.,\s]', '', amount[0]))
        if period:
            context.setdefault('billing_period', period[0])
        if region:
            context.setdefault('region', region[0])
        if effective:
            context.setdefault('effective_date', effective[1])
        missing = {k: v for k, v in context.items() if norm(v) in norm(page.text) and norm(v) not in norm(excerpt)}
        unsupported = {k: v for k, v in context.items() if norm(v) not in norm(page.text)}
        dimensions = {k: {'expected': context.get(k), 'recoverable': (norm(context[k]) in norm(excerpt)) if k in context else None}
                      for k in dict.fromkeys(('entity', 'value', 'unit', 'billing_period', 'region', 'effective_date', 'exceptions', *context))}
        items = [evidence(page.url, block['text'], locator=block['locator'], observed_at=page.observed_at)]
        items += [evidence(page.url, str(v), locator='context outside selected excerpt') for v in missing.values()]
        results.fact_tests.append({'question': question, 'inferred': fact.get('inferred', False), 'status': 'unknown' if unsupported else 'fail' if missing else 'unknown' if not context.get('entity') or (amount and context.get('unit') in (None, '$')) else 'pass',
            'excerpt': excerpt, 'dimensions': dimensions, 'missing_context': missing, 'unsupported_context': unsupported,
            'representations': {'raw_html': 'matched', 'rendered': {name: all(t in norm(r['text']) for t in terms) for name, r in page.rendered.items()}},
            'limitation': 'Deterministic term/context preservation, not a semantic answer correctness score.', 'evidence_items': items})
        # Inferred "only" clauses in unrelated FAQs are review leads. Explicit
        # billing/eligibility sections tied to a single offer remain testable.
        conditions = [b for b in page.blocks if re.search(r'condition|billing|eligibility|terms|exception', b['heading'], re.I)]
        grounded = not fact.get('inferred') or all(any(norm(v) in norm(b['text']) for b in conditions) for v in missing.values())
        if missing and not grounded:
            results.fact_tests[-1]['status'] = 'unknown'
            results.review('facts.context_scope', page.url, question,
                'Extracted clauses may qualify other offers or FAQ answers; their applicability is not established.', items)
        if missing and grounded:
            results.finding('facts.context_loss', page.url, 'An isolated fact excerpt loses qualifying context',
                excerpt + ' | Missing context: ' + json.dumps(missing, ensure_ascii=False),
                'Keep the answer, entity, units and applicable conditions in the same accessible content block.',
                'Repeat this question against the isolated section with its heading and table headers.',
                entity=question, items=items, confidence='medium', reason='Caller-supplied qualifying context is present on the page but absent from the matching section; review applicability.')
            # Extractive rewrite: only joins existing evidence; no invented facts or conditions.
            rewrite = excerpt + ' ' + ' '.join(str(v) for v in missing.values())
            preserved = all(norm(s) in norm(rewrite) for s in [excerpt] + list(missing.values()))
            results.rewrites.append({'question': question, 'original': excerpt, 'proposed_rewrite': rewrite,
                                    'all_source_spans_preserved': preserved, 'missing_before': list(missing),
                                    'missing_after': [k for k, v in context.items() if norm(v) not in norm(rewrite)],
                                    'evidence_items': items, 'result': 'Extractive draft only; span inclusion is not an independent answer-quality test. Review applicability before publishing'})
    if not facts:
        results.check('facts.stress_test', '', 'unknown', 'No supported automatic candidates; use the review queue to build evidence questions.')
        if pages:
            results.review('facts.questions', pages[0].url, 'Which concrete visitor questions should this website answer?',
                'Automatic patterns did not produce supported questions for this content or language.',
                [evidence(pages[0].url, pages[0].main_text[:700])],
                'Read the selected-locale homepage and primary service/product page; form questions from published facts, then use --facts-file with exact evidence terms and qualifications.')


def compare_claims(claims, results):
    for i, left in enumerate(claims):
        for right in claims[i + 1:]:
            if left['source_url'] == right['source_url'] or (norm(left['entity']), left['attribute']) != (norm(right['entity']), right['attribute']):
                continue
            state, reason = 'unknown', 'Scope is insufficient to establish equivalent claims.'
            if left['region'] and right['region'] and left['region'] != right['region']:
                state, reason = 'regional_difference', 'Explicit regions differ.'
            elif left['effective_date'] and right['effective_date'] and left['effective_date'] != right['effective_date']:
                state, reason = 'historical_difference', 'Explicit effective dates differ.'
            elif all(left[k] == right[k] for k in ('region', 'effective_date', 'exceptions', 'billing_period', 'unit')):
                if left['value'] == right['value']:
                    state, reason = 'consistent', 'Matching extracted value and available scope; not proof of correctness.'
                elif left['region'] and left['effective_date'] and left['unit'] != 'dollar_unspecified':
                    state, reason = 'contradiction', 'Same entity, attribute, date, region, unit, billing and stated exceptions; different values.'
            items = [evidence(c['source_url'], c['evidence_span'], observed_at=c['observed_at']) for c in (left, right)]
            results.comparisons.append({'entity': left['entity'], 'attribute': left['attribute'], 'status': state, 'reason': reason, 'evidence_items': items})
            if state == 'contradiction':
                results.finding('claims.contradiction', left['source_url'], 'Equivalent claims disagree',
                    left['value'] + ' versus ' + right['value'], 'Resolve which claim applies and update all affected pages with its scope.',
                    'Re-extract both claims and compare value, region, effective date and exceptions.',
                    severity='high', entity=left['entity'], root_cause=left['attribute'], items=items,
                    confidence='medium', reason='Deterministic scoped extraction; confirm product-specific exclusions before changing content.')


def pdf_check(response, results, target_facts):
    url = response['url']
    from .crawl import header_checks
    header_checks(url, response.get('headers', {}), results)
    try:
        from pypdf import PdfReader
    except ImportError:
        results.check('media.pdf_text', url, 'not_run', 'Optional pypdf is unavailable.')
        return
    try:
        reader = PdfReader(io.BytesIO(response['body']))
        text = '\n'.join(p.extract_text() or '' for p in reader.pages[:20])
        results.check('media.pdf_text', url, 'pass' if text.strip() else 'unknown',
                      'Extracted text from up to 20 pages.' if text.strip() else 'No extractable text; possibly scanned. OCR/visual verification was not run.',
                      [evidence(url, text[:1500], 'pdf_text')])
        if not text.strip():
            results.suggest('media.pdf_accessibility', url, 'No text extracted from the sampled PDF pages.',
                            'Inspect for scanned content and provide a verified text equivalent if needed.', 'Extract the same facts from the accessible document and confirm them visually.')
    except Exception as exc:
        results.check('media.pdf_text', url, 'unknown', 'PDF parsing failed: ' + str(exc))
