"""Compact business-owner report; detailed evidence stays inside the audit."""
import re
import unicodedata
from urllib.parse import urlsplit

PRIORITY = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}


def report_filename(site, brand=None):
    host = urlsplit(site).hostname or 'website'
    parts = host.removeprefix('www.').split('.')
    # Country domains such as example.co.in keep the company label.
    index = -3 if len(parts) > 2 and len(parts[-1]) == 2 and parts[-2] in {'co','com','net','org','gov','edu','ac'} else -2
    fallback = parts[index] if len(parts) > 1 else parts[0]
    name = brand if brand and brand != host else fallback
    stem = re.sub(r'[^\w]+', '_', unicodedata.normalize('NFKC', name).casefold()).strip('_')
    stem = (stem or fallback)[:80].rstrip('_')
    return stem + '_report.json'


def priority_summary(items, field, total):
    return {total: len(items), **{p: sum(item[field] == p for item in items) for p in PRIORITY}}


def short_evidence(value):
    text = ' '.join(value.split())
    return text if len(text) <= 400 else text[:399].rsplit(' ', 1)[0] + '…'


def owner_report(report, component=None):
    from .runner import merge_findings

    def selected(item):
        check = item['check_id']
        engagement = item.get('category') == 'engagement' or check.startswith('journey.')
        if component == 'engagement':
            return engagement
        if component == 'freshness':
            return check.startswith(('freshness.', 'claims.', 'identity.', 'facts.'))
        return component != 'crawl' or not engagement

    groups = {}
    for finding in merge_findings([f for f in report['findings'] if selected(f)]):
        key = (finding['check_id'], finding['entity'], finding['root_cause'],
               finding['title'], finding['suggested_action']['summary'])
        if key not in groups:
            groups[key] = {'title': finding['title'], 'severity': finding['severity'],
                'evidence': short_evidence(finding['evidence']),
                'suggested_action': {k: finding['suggested_action'][k] for k in ('summary', 'priority', 'verification') if k in finding['suggested_action']},
                'pages': list(finding['affected_urls'])}
        else:
            item = groups[key]
            item['pages'] = list(dict.fromkeys(item['pages'] + finding['affected_urls']))
    findings = [{'id': f'F-{i:03d}', **finding} for i, finding in enumerate(groups.values(), 1)]
    result = {'site': report['site'], 'audited_at': report['audited_at'],
        'summary': priority_summary(findings, 'severity', 'total_findings'),
        'improvements_summary': priority_summary([], 'priority', 'total_improvements'),
        'findings': findings}

    improvements = {}
    for suggestion in report.get('proactive_suggestions', []):
        if not selected(suggestion):
            continue
        action = suggestion['suggested_action']
        key = (suggestion['check_id'], action['summary'])
        item = {'summary': action['summary'], 'priority': action['priority'],
            'evidence': short_evidence('; '.join(i['quote'] for i in suggestion['evidence_items'])),
            'page': suggestion['resource']}
        if action.get('verification'):
            item['verification'] = action['verification']
        if key not in improvements or PRIORITY[item['priority']] < PRIORITY[improvements[key]['priority']]:
            improvements[key] = item
    if improvements:
        result['improvements'] = sorted(improvements.values(), key=lambda i: PRIORITY[i['priority']])[:3]
        result['improvements_summary'] = priority_summary(result['improvements'], 'priority', 'total_improvements')

    metadata = report['run_metadata']
    stages = metadata.get('stage_status', {})
    checks = report['checks']
    incomplete = any(s in ('partial', 'not_run', 'pending') for s in stages.values()) or any(
        c['status'] in ('unknown', 'not_run') and
        ('.budget' in c['check_id'] or '.internal_error' in c['check_id'] or
         c['check_id'].startswith(('stage.', 'render.browser', 'access.fetch', 'run.', 'collection.locale')))
        for c in checks)
    if not metadata['pages_audited']:
        result['note'] = 'The website could not be assessed; no issues were verified.'
    elif incomplete:
        result['note'] = 'Some pages or interactions could not be verified; further issues may remain.'
    return result
