"""Question-specific, read-only engagement evidence and owner reporting."""
import re
from urllib.parse import urlsplit, urljoin, urlencode, parse_qsl, urlunsplit
from .collection import BudgetExceeded
from .diagnostics import Page, evidence, norm
from .scope import SiteScope


def page_purpose(page):
    from .scope import url_locale
    path = urlsplit(page.url).path.lower()
    prefix = url_locale(page.url)[2]
    local_path = '/' + path[len(prefix):] if prefix and path.startswith(prefix) else path
    if re.search(r'/return|/refund|/exchange', path):
        return 'returns'
    if re.search(r'/shipping|/delivery', path):
        return 'delivery'
    if re.search(r'/contact|/support|/help|/faq|/customer-service/?$', path) and not re.search(r'/article', path):
        return 'support'
    types = {t for n in page.nodes for t in (n.get('@type', []) if isinstance(n.get('@type'), list) else [n.get('@type')]) if isinstance(t, str)}
    if re.search(r'/about|/polic', path):
        return 'informational'
    if types & {'Article', 'BlogPosting', 'NewsArticle'} or re.search(r'/blog|/article|/news', path):
        return 'article'
    if re.search(r'/docs?(?:/|$)|/reference|/tutorial', path):
        return 'documentation'
    if local_path in ('', '/'):
        return 'homepage'
    if re.search(r'/products?/|/p/', path):
        return 'product'
    if re.search(r'/cat/|/category/|/collections?/', path):
        return 'category'
    if 'Product' in types or 'ProductGroup' in types:
        return 'product'
    if re.search(r'/pricing|/plans(?:/|$)', path):
        return 'pricing'
    if types & {'Service', 'ProfessionalService'} or re.search(r'/services?(?:/|$)', path):
        return 'service'
    return 'homepage' if local_path in ('', '/') else 'informational'


QUESTIONS = {
    'product': [('budget', 'What does this product cost?', r'price|pricing|cost|कीमत', [r'(?:₹|INR|USD|EUR|GBP|\$|€|£)\s*\d']),
                ('suitability', 'Does this product meet my requirements?', r'spec|size|dimension|compatib|material', [r'\b(?:size|dimensions?|material|compatible|capacity|weight)\b']),
                ('returns', 'What return conditions apply?', r'return|refund|exchange|वापसी', [r'return|refund|exchange|वापसी', r'\b\d+\s*(?:business\s*)?days?\b|non.returnable|no returns|final sale'])],
    'pricing': [('plans', 'How do the plans and commitments compare?', r'pricing|plans|compare', [r'(?:₹|INR|USD|EUR|GBP|\$|€|£)\s*\d', r'month|year|one.time|per seat|per user', r'includ|limit|feature'])],
    'service': [('service', 'What does this service cover and how do I enquire?', r'service|contact|enquir|book', [r'service|consult|support', r'contact|enquir|book'])],
    'documentation': [('documentation', 'Can I find instructions for the task?', r'guide|tutorial|start|reference|search', [r'step|example|usage|install|configure'])],
    'article': [('article', 'Can I identify what this article explains?', r'related|read|source|reference', [r'\b(?:how|why|guide|learn|explain|steps?|research|report|announc)\w*\b'])],
    'homepage': [('orientation', 'What does this business offer and where do I go next?', r'product|shop|service|explore|learn|browse|catalog', [r'product|shop|service|furniture|software|solutions?|offer|provide|build|sell|design|manufactur'])]
}


QUESTIONS.update({
    'category': [('selection', 'Which available item meets my needs?', r'/p/|product|filter|sort|compare', [r'price|product|filter|sort|compare|₹|INR|USD|EUR'])],
    'returns': [('returns', 'When and how can I return an item?', r'return|refund|exchange', [r'return|refund|exchange|वापसी', r'\d+\s*(?:business\s*)?days?|non.returnable|final sale'])],
    'delivery': [('delivery', 'Where do you deliver and what timing or charges apply?', r'deliver|shipping|coverage|postcode|pincode', [r'deliver|shipping|डिलीवरी', r'days?|charge|fee|free|postcode|pincode|area|city|region'])],
    'support': [('support', 'How can I get help with this issue?', r'contact|help|support|faq|phone|email', [r'contact|help|support|phone|email|call|संपर्क'])],
    'informational': [('information', 'What does this page explain and where can I find details?', r'about|detail|policy|learn|contact|guide', [r'about|policy|provide|offer|help|contact|learn|guide|information'])],
})


def assess_answer(text, criteria):
    matched = [bool(re.search(pattern, text, re.I)) for pattern in criteria]
    return all(matched), matched


def engagement_checks(page, results, collector=None, rendered_only=False):
    purpose = page_purpose(page)
    navigation_scope = collector.scope if collector and collector.scope else SiteScope(page.url)
    # Structural observations apply across languages. Missing-answer suggestions
    # require a matching language rule set; unfamiliar text goes to source review.
    language = page.lang.replace('_','-').split('-')[0]
    supported_semantics = language in ('en','hi')
    if not rendered_only:
        results.check('journey.purpose', page.url, 'pass', 'Evidence-selected purpose: ' + purpose)
        viewport = page.soup.select_one('meta[name="viewport"]')
        if viewport:
            settings = {part.split('=',1)[0].strip().lower():part.split('=',1)[1].strip().lower() for part in viewport.get('content','').split(',') if '=' in part}
            scale = settings.get('maximum-scale', '')
            restricted = settings.get('user-scalable') in ('no', '0') or (bool(re.fullmatch(r'\d+(?:\.\d+)?',scale)) and float(scale) < 2)
            if restricted:
                results.finding('journey.zoom', page.url, 'Page settings request restricted magnification',
                    str(viewport), 'Remove restrictive user-scalable or maximum-scale settings so visitors can enlarge the page.',
                    'Inspect the viewport declaration and verify magnification on a mobile device.', category='engagement', severity='low')
        results.check('journey.personalization', page.url, 'not_applicable', 'Anonymous sample; returning-user personalization is not established.')
        results.check('performance.field', page.url, 'not_applicable', 'No representative real-user measurements supplied.')
        search_forms = page.soup.select('form[role=search],form:has(input[type=search])')
        results.check('journey.search', page.url, 'unknown' if search_forms else 'not_applicable', 'Search interface detected; only explicitly GET-based same-origin search can be sampled.' if search_forms else 'No explicit search interface found; search is not mandatory.')
        if collector and search_forms:
            form = search_forms[0]
            field = form.select_one('input[type=search][name],input[name=q],input[name=query],input[name=s]')
            heading = page.soup.select_one('h1')
            term = heading.get_text(' ', strip=True)[:100] if heading else ''
            action = urlsplit(urljoin(page.url, form.get('action') or page.url))
            if field and term and form.get('method', 'get').lower() == 'get' and navigation_scope.allows(action.geturl()):
                query = dict(parse_qsl(action.query));query[field['name']] = term
                target = urlunsplit((action.scheme, action.netloc, action.path, urlencode(query), ''))
                try:
                    response = collector.fetch(target)
                    results.check('journey.search_response', target, 'unknown', 'Anonymous GET search sampled; result relevance and visibility require review.', [evidence(page.url, 'Search term from page heading: ' + term)])
                    if response.get('status') in (404, 410):
                        results.finding('journey.broken_search', page.url, 'The public search endpoint returns an error',
                            f'GET {target} returned HTTP {response["status"]}.', 'Repair the search form destination or restore its public GET endpoint.',
                            'Repeat the same public search and inspect its results.', category='engagement')
                except BudgetExceeded:
                    results.check('journey.search_response', target, 'not_run', 'Search allowance exhausted; existing evidence retained.')
        for key, question, link_pattern, criteria in QUESTIONS.get(purpose, []):
            related = [a for a in page.links if re.search(link_pattern, a['name'] + ' ' + urlsplit(a['url']).path, re.I) and navigation_scope.allows(a['url'])]
            identity = next((n.get('name') for n in page.nodes if n.get('@type') == 'Product' and n.get('name')), None)
            journey = {'product_context': identity, 'source_url': page.url, 'question': question, 'needed_information': key,
                'status': 'unknown', 'reason': 'Raw HTML is a discovery lead; rendered visibility has not been verified.',
                'public_navigation_candidates': related[:3], 'evidence_items': [], 'destination_answers': []}
            for link in related[:2]:
                if not collector or not link['url'].startswith(('http://', 'https://')):
                    continue
                try:
                    response = collector.fetch(link['url'])
                except BudgetExceeded:
                    results.check('journey.public_path', link['url'], 'not_run', 'Path request budget exhausted; collected observations retained.')
                    break
                if response.get('status') in (404, 410):
                    results.finding('journey.broken_information_link', page.url, 'An information link leads to an error page',
                        f"{link['name']} links to {link['url']}, which returned HTTP {response['status']}.",
                        'Correct this link or restore the promised information at its destination.',
                        'Follow the public link and verify the promised answer.', category='engagement', entity=link['url'])
                    journey.update(status='fail', reason='A relevant information link returned an HTTP error.')
                elif response['state'] == 'ok' and 'html' in response.get('headers', {}).get('content-type', 'text/html'):
                    destination = Page(response)
                    if collector.scope and not collector.scope.accepts_document(destination):
                        continue
                    if hasattr(collector, 'followup_pages'):
                        collector.followup_pages[destination.url] = destination
                    found, matched = assess_answer(destination.main_text, criteria)
                    target_names = [n.get('name') for n in destination.nodes if n.get('@type') == 'Product' and n.get('name')]
                    scope_matches = not target_names or (identity and any(norm(n) == norm(identity) for n in target_names))
                    item = {'context_status': 'unknown' if not identity else 'retained' if scope_matches else 'different_product', 'url': destination.url, 'answer_candidate': found, 'matched_criteria': matched,
                        'status': 'unknown', 'reason': 'Destination HTML retrieved; visible answer, product scope and exceptions require verification.'}
                    if re.search(r'page not found|404 not found|access denied', destination.main_text[:200], re.I):
                        item['answer_candidate'] = False
                        item['reason'] = 'Destination content resembles an error despite HTTP success.'
                    if target_names and not scope_matches:
                        item.update(answer_candidate=False, reason='Destination names a different product; it does not verify the original product question.')
                    journey['destination_answers'].append(item)
                else:
                    results.check('journey.public_path', link['url'], 'unknown', 'Destination unavailable; no successful information path inferred.')
            results.journeys[:] = [j for j in results.journeys if (j['source_url'], j['question']) != (journey['source_url'], journey['question'])]
            results.journeys.append(journey)
            results.reviews[:] = [r for r in results.reviews if not (r['check_id']=='journey.answer' and
                r['source_url']==page.url and r['question']==question)]
            if not assess_answer(page.main_text, criteria)[0] and not any(d.get('answer_candidate') for d in journey['destination_answers']):
                results.review('journey.answer', page.url, question,
                    'No applicable answer established from the sampled page and public information destinations.',
                    [evidence(page.url, page.main_text[:500])],
                    'Inspect the relevant same-locale information link or visible disclosure for this question; verify its subject and conditions before recommending a change.')
    for viewport, sample in page.rendered.items():
        reliable = sample.get('visual_reliable', sample.get('reliable', not sample.get('blocked_requests') and not sample.get('request_errors')))
        absence_reliable = sample.get('absence_reliable', reliable)
        results.check('journey.render_quality.' + viewport, page.url, 'pass' if reliable else 'unknown',
            'Stable anonymous instrumented sample.' if reliable else 'Rendering incomplete or unstable; no visual defect or success inferred.')
        if not reliable:
            continue
        for journey in [j for j in results.journeys if j['source_url'] == page.url]:
            definition = next((q for q in QUESTIONS.get(purpose, []) if q[1] == journey['question']), None)
            if not definition:
                continue
            # Answer criteria must co-occur in one visible section, not unrelated page tokens.
            answers = [b for b in sample.get('content', []) if not b.get('obstructed') and assess_answer(b['text'], definition[3])[0]]
            journey.setdefault('viewports', {})[viewport] = {'status': 'pass' if answers else 'unknown',
                'reason': 'Visible answer candidate meets the stated lexical criteria; applicability is not a semantic guarantee.' if answers else 'No coherent visible answer matched in this bounded sample.',
                'evidence': [b['text'][:400] for b in answers[:2]]}
            if not answers and absence_reliable and supported_semantics and not journey['public_navigation_candidates']:
                results.suggest('journey.answer_path.' + journey['needed_information'], page.url, 'No answer or relevant information link found for: ' + journey['question'],
                    'Add a concise answer or a clearly labelled link for this visitor question: ' + journey['question'],
                    'Repeat this question in the same viewport and confirm the answer includes its conditions.', priority='medium')
            if not answers:
                results.review('journey.answer', page.url, journey['question'],
                    'No visible answer established in this viewport; destination candidates are retained in the journey evidence.',
                    [evidence(page.url, str(journey.get('destination_answers', [])), 'navigation')])
            if answers and journey['status'] != 'fail':
                journey.update(status='pass', reason='A coherent visible answer candidate was located; see viewport scope and evidence.')
                results.reviews[:] = [r for r in results.reviews if not (r['check_id']=='journey.answer' and
                    r['source_url']==page.url and r['question']==journey['question'])]
        actions = sample.get('actions', [])
        relevant = [a for a in actions if a.get('relevant')]
        usable = [a for a in relevant if a.get('enabled') and a.get('in_viewport') and not a.get('obstructed')]
        results.check('journey.actions.' + viewport, page.url, 'pass' if usable else 'unknown',
            'An enabled, visible next-step candidate receives pointer events; submission/navigation was not executed.' if usable else 'No usable task action established; unavailable states and prerequisites need review.')
        if not relevant and absence_reliable and supported_semantics and purpose in ('product','pricing','service','homepage'):
            results.suggest('journey.next_step', page.url, 'No task-relevant control observed in the sampled viewport and scroll positions.',
                'Make the next step for this page visible and descriptive, such as viewing options, comparing plans or contacting the service.',
                'Inspect the same page on desktop and mobile; verify the next step preserves the selected product and locale.', priority='medium')
        for action in relevant:
            if not action.get('in_viewport') or not action.get('enabled') or not action.get('obstructed'):
                continue
            locator = action['locator']
            quote = f"On {viewport}, {action['name']!r} ({locator}) is blocked by {action.get('blocker')}; bounds {action.get('rect')}."
            results.finding('journey.obstructed_action', page.url, 'A next-step control is covered by another element', quote,
                'Adjust the identified overlay or stacking order so this control can be reached; preserve any required consent choice.',
                'Repeat the same viewport and inspect the control after the page settles.', category='engagement', entity=locator,
                items=[evidence(page.url, quote, 'rendered_' + viewport, locator)])
        for offender in sample.get('overflow_elements', []):
            quote = f"On {viewport}, text in {offender['locator']} extends outside the viewport: {offender['text'][:120]} (bounds {offender['rect']})."
            results.finding('journey.horizontal_overflow', page.url, 'Reading essential text requires horizontal scrolling', quote,
                'Constrain the identified text container and wrap long content within the viewport.',
                'Check the same text at narrow widths and enlarged text sizes.', category='engagement', entity=offender['locator'])
        for action in actions:
            if not action.get('name') and action.get('in_viewport'):
                results.finding('journey.unnamed_control', page.url, 'A visible control has no accessible name',
                    f"On {viewport}, {action['locator']} has no accessible name.",
                    'Give this control a descriptive visible label or accessible name that explains its action.',
                    'Inspect the accessibility tree and confirm keyboard users can identify the control.', category='engagement', severity='medium', entity=action['locator'])
        small = [a for a in relevant if a.get('in_viewport') and min(a['rect']['width'], a['rect']['height']) < 24]
        if viewport == 'mobile' and small:
            results.suggest('journey.target_size', page.url, ', '.join(a['locator'] for a in small[:3]),
                'Review these small controls for sufficient touch area or spacing; check applicable target-size exceptions.',
                'Measure target area and spacing on a touch viewport.')
        results.check('journey.keyboard.' + viewport, page.url, 'pass' if sample.get('keyboard_focus') else 'unknown',
            'A bounded Tab-key sample reached focusable controls; complete focus order and trap freedom are not established.')
        results.check('journey.disclosures.' + viewport, page.url, 'unknown' if any(d.get('status') == 'unknown' for d in sample.get('disclosures', []) if isinstance(d, dict)) else 'pass' if sample.get('disclosures') else 'not_applicable',
            'Local disclosure states sampled without form submission; site search and transactional workflows were not submitted.')


def compact_report(report, engagement_only=True):
    from .reporting import owner_report
    return owner_report(report, 'engagement' if engagement_only else None)
