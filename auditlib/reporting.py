"""One small business-facing projection for every entrypoint; diagnostics stay separate."""

def owner_report(report, component=None):
    from .runner import merge_findings
    def selected(f):
        if component == 'engagement':
            return f.get('category') == 'engagement'
        if component == 'freshness':
            return f['check_id'].startswith(('freshness.','claims.','identity.'))
        return component != 'crawl' or f.get('category') != 'engagement'
    findings = []
    for f in merge_findings([f for f in report['findings'] if selected(f)]):
        explanation = f['evidence'].strip()
        if f['resource'] and f['resource'] not in explanation:
            explanation += ' Source: ' + f['resource']
        findings.append({'id':f['id'], 'title':f['title'], 'severity':f['severity'], 'evidence':explanation,
            'suggested_action':{k:f['suggested_action'][k] for k in ('summary','priority')}})
    stages = dict(report['run_metadata'].get('stage_status', {}))
    checks = report['checks']
    incomplete = any(c['status'] in ('unknown','not_run') for c in checks)
    incomplete |= any(v in ('pending','partial','not_run') for v in stages.values())
    incomplete |= not report['run_metadata']['pages_audited']
    limitations = ['Finite anonymous sample; findings describe observed defects, not rankings, traffic, conversion rates or commercial AI visibility.']
    for stage, status in stages.items():
        if status in ('partial','not_run','pending'):
            limitations.append(stage.capitalize() + ' coverage is incomplete.')
    if any(c['check_id'].startswith('render') and c['status'] in ('unknown','not_run') for c in checks):
        limitations.append('Browser coverage is incomplete; unavailable checks are not evidence of a healthy page.')
    if any(c['check_id'].startswith('external') and c['status'] in ('unknown','not_run') for c in checks):
        limitations.append('External discoverability was not fully verified from an independent source sample.')
    coverage = {'status':'partial' if incomplete else 'sampled', 'pages_inspected':len(report['run_metadata']['pages_audited']), 'limitations':limitations}
    if stages:
        coverage['components'] = stages
    return {'site':report['site'], 'audited_at':report['audited_at'],
        'summary':{'total_findings':len(findings), **{s:sum(f['severity']==s for f in findings) for s in ('critical','high','medium','low')}},
        'findings':findings, 'coverage':coverage,
        'suggested_actions':[{'summary':s['suggested_action']['summary'], 'priority':s['suggested_action']['priority'], 'evidence':s['evidence_items'][0]['quote']}
            for s in report.get('proactive_suggestions', []) if component != 'engagement' or s['check_id'].startswith('journey.')][:3]}
