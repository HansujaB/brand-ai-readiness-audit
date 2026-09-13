"""Shared orchestration, partial reports, validation, and bounded CLI execution."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from xml.etree import ElementTree

from .collection import Collector, BudgetExceeded, normalize, origin, utcnow, excluded_url
from .diagnostics import (Page, Results, candidates, stress_tests,
                          crawl_checks, pdf_check, evidence, norm)
from .browser import render_pages
from .engagement import engagement_checks
from .freshness import check_freshness, check_article_dates, extract_product_claims, prioritize_links
from .identity import identity_checks, published_brand
from .scope import SiteScope, COUNTRIES, LANGUAGES, language_tag
from .freshness import extract_policy_claims, compare_site_claims

ROOT = Path(__file__).resolve().parents[1]


def merge_findings(findings):
    merged = {}
    severity = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    for original in findings:
        finding = copy.deepcopy(original)
        key = (finding['check_id'], norm(finding['entity']), finding['resource'], finding['root_cause'])
        if key not in merged:
            merged[key] = finding
        else:
            current = merged[key]
            current['affected_urls'] = sorted(set(current['affected_urls'] + finding['affected_urls']))
            existing = {json.dumps(e, sort_keys=True) for e in current['evidence_items']}
            current['evidence_items'].extend(e for e in finding['evidence_items'] if json.dumps(e, sort_keys=True) not in existing)
            if severity[finding['severity']] < severity[current['severity']]:
                current['severity'] = finding['severity']
                current['suggested_action'] = finding['suggested_action']
                current['evidence'] = finding['evidence']
    ordered = sorted(merged.values(), key=lambda f: (severity[f['severity']], {'low': 0, 'medium': 1, 'high': 2}[f['suggested_action']['effort']], f['check_id'], f['resource']))
    for finding in ordered:
        finding['suggested_action']['priority'] = 'high' if finding['severity'] == 'critical' else finding['severity']
        identity = json.dumps([finding['check_id'], norm(finding['entity']), finding['resource'], finding['root_cause']])
        finding['id'] = 'F-' + hashlib.sha256(identity.encode()).hexdigest()[:12]
    return ordered


def validate_report(report):
    import jsonschema
    schema = json.loads((ROOT / 'skills/audit-orchestrator/references/report.schema.json').read_text(encoding='utf-8-sig'))
    jsonschema.validate(report, schema)
    assert report['summary']['total_findings'] == len(report['findings'])
    for severity in ('critical', 'high', 'medium', 'low'):
        assert report['summary'][severity] == sum(f['severity'] == severity for f in report['findings'])


def snapshot(site, brand, collector, results, pages, capabilities, work_budget):
    findings = merge_findings(results.findings)
    checks = list({json.dumps(c, sort_keys=True): c for c in results.checks}.values())
    return {'site': site, 'brand': brand, 'audited_at': utcnow(),
        'run_metadata': {'pages_audited': [p.url for p in pages],
            'scope': collector.scope.as_dict() if collector.scope else {},
            'browser_samples': [{'url': p.url, 'viewports': p.rendered} for p in pages if p.rendered],
            'capabilities_used': capabilities, 'elapsed_seconds': round(time.monotonic() - collector.started, 3), 'stages_completed': getattr(results, 'completed_stages', []),
            'work_budget_seconds': work_budget, 'stage_status': getattr(results, 'stage_status', {}),
            'download_budget': {'max_response_bytes': collector.max_response_bytes, 'max_download_bytes': collector.max_download_bytes,
                                'decoded_bytes_received': collector.downloaded_bytes, 'byte_basis': 'decoded response bodies; cache hits counted once'},
            'request_count': len(collector.log), 'request_log': collector.log,
            'evidence_store': [{'url': url, 'state': r['state'], 'observed_at': r.get('observed_at'), 'sha256': r.get('sha256'),
                                'status': r.get('status'), 'reason': r.get('reason'), 'bytes_received': r.get('bytes_received'),
                                'limit_scope': r.get('limit_scope'), 'truncated': r.get('truncated', False)} for url, r in collector.cache.items()],
            'limitations': ['Finite anonymous sample; no inference about actual bounce rates, rankings, or commercial assistant visibility.',
                           'Each connection uses a validated public IP with original TLS hostname verification; redirects are checked again.',
                           'Browser request delivery uses cached audit evidence; lab timings are instrumented observations.']},
        'summary': {'total_findings': len(findings), **{s: sum(f['severity'] == s for f in findings) for s in ('critical', 'high', 'medium', 'low')}},
        'findings': findings, 'checks': checks, 'proactive_suggestions': sorted({(s['check_id'], s['resource']):s for s in results.suggestions}.values(), key=lambda s: ({'high':0,'medium':1,'low':2}.get(s['suggested_action']['priority'],0), not s['check_id'].startswith('journey.'), s['check_id'], s['resource'])),
        'fact_extraction_tests': results.fact_tests, 'claims': results.claims, 'claim_comparisons': results.comparisons,
        'visitor_journeys': results.journeys, 'local_rewrite_tests': results.rewrites, 'review_queue': results.reviews}


def audit(site, brand=None, facts=None, extra_pages=None, browser=True,
          budget=270, collector=None, checkpoint=None, component=None, max_response_bytes=20_000_000,
          max_download_bytes=100_000_000, country=None, language=None, max_requests=400):
    site = normalize(site)
    collector = collector or Collector(seconds=budget, max_requests=max_requests,
        max_response_bytes=max_response_bytes, max_download_bytes=max_download_bytes)
    scope = collector.scope = SiteScope(site, country, language)
    collector.followup_pages = {}
    results, pages = Results(), []
    capabilities = {'python_execution': True, 'headless_browser': False, 'website_only': True}
    stages = ['collection', 'crawl', 'render', 'facts', 'claims', 'engagement']
    required = {'collection'}
    if component in (None, 'crawl'):
        required.update(('crawl', 'render', 'facts'))
    if component in (None, 'freshness'):
        required.update(('claims', 'facts'))
    if component in (None, 'engagement'):
        required.update(('engagement', 'render'))
    results.stage_status = {stage: 'pending' if stage in required else 'not_applicable' for stage in stages}
    results.completed_stages = []
    def report():
        return snapshot(site, brand, collector, results, pages, capabilities, budget)
    def save():
        if checkpoint:
            checkpoint(report())
    def safe(stage, url, operation):
        try:
            return operation()
        except BudgetExceeded as exc:
            results.check(stage + '.budget', url, 'not_run', str(exc))
        except Exception as exc:
            results.check(stage + '.internal_error', url, 'unknown', type(exc).__name__ + ': ' + str(exc)[:300])
        finally:
            save()
        results.stage_status[stage] = 'partial'
    def finish(stage):
        if stage not in results.completed_stages:
            results.completed_stages.append(stage)
        if results.stage_status[stage] != 'partial':
            results.stage_status[stage] = 'sampled'
        save()
    save()
    limit = 12
    queue, attempted, collected = [site] + list(extra_pages or []), set(), set()
    discovery_done = False

    def inspect(page):
        page.audit_scope = scope.as_dict()
        pages.append(page)
        collected.add(page.url)
        results.check('access.fetch', page.url, 'pass', 'Public HTML page collected in the selected locale.',
            [evidence(page.url, 'HTTP ' + str(page.response.get('status', 200)), 'http')])
        if 'crawl' in required:
            safe('crawl', page.url, lambda: crawl_checks(page, results, collector))
        if 'claims' in required:
            def claims_for_page():
                results.claims.extend(extract_product_claims(page, brand))
                results.claims.extend(extract_policy_claims(page, brand))
                check_freshness(page, results)
                check_article_dates(page, results)
            safe('claims', page.url, claims_for_page)
        if 'engagement' in required:
            safe('engagement', page.url, lambda: engagement_checks(page, results))
        save()

    def discover_sitemaps(base):
        declared = collector.policy(base).sitemaps or [origin(base) + '/sitemap.xml']
        sitemap_queue = sorted((u for u in declared if scope.allows(u, 'sitemap')), key=scope.rank)
        visited = set()
        while sitemap_queue and len(visited) < 4:
            url = normalize(sitemap_queue.pop(0))
            if url in visited or not scope.allows(url, 'sitemap'):
                continue
            visited.add(url)
            response = collector.fetch(url, purpose='sitemap')
            if response['state'] != 'ok':
                results.check('access.sitemap', url, 'not_applicable' if response.get('status') in (404, 410) else 'unknown',
                    response.get('reason', 'Sitemap unavailable; linked pages remain usable.'))
                continue
            try:
                xml = ElementTree.fromstring(response['body'])
                tag = xml.tag.split('}')[-1]
                if tag not in ('urlset', 'sitemapindex'):
                    raise ValueError('Expected urlset or sitemapindex root')
                locs = [e.text.strip() for e in xml.iter() if e.tag.split('}')[-1] == 'loc' and e.text and e.text.strip()]
                purpose = 'sitemap' if tag == 'sitemapindex' else 'page'
                locs = sorted((u for u in locs if scope.allows(u, purpose)), key=scope.rank)
                if tag == 'sitemapindex':
                    sitemap_queue.extend(locs)
                else:
                    queue.extend(prioritize_links(locs)[:limit * 4])
                results.check('access.sitemap', url, 'pass', 'Parsed sitemap; only selected-locale URLs enter discovery.')
            except (ElementTree.ParseError, ValueError) as exc:
                results.finding('access.sitemap_invalid', url, 'Published sitemap is malformed', str(exc),
                    'Repair the sitemap XML and its document type.', 'Validate this sitemap and its children.', severity='low')

    def collect():
        nonlocal discovery_done, brand
        while len(collected) < limit and len(attempted) < limit * 4:
            collector.remaining()
            if not queue:
                if discovery_done or not pages:
                    break
                discovery_done = True
                # Discovery cannot consume the browser's download allowance.
                with collector.allowance(min(8, budget * .08), 6, bytes=2_000_000):
                    safe('collection', pages[0].url, lambda: discover_sitemaps(pages[0].url))
                if not queue:
                    break
            raw = queue.pop(0)
            try:
                url = normalize(raw)
            except (ValueError, TypeError) as exc:
                results.check('collection.invalid_link', str(raw), 'unknown', str(exc))
                continue
            if url in attempted or url in collected or not scope.allows(url) or excluded_url(url):
                continue
            attempted.add(url)
            response = safe('collection', url, lambda: collector.fetch(url))
            if not response:
                continue
            if response['state'] != 'ok':
                results.check('access.fetch', url, 'not_run' if response['state'] in ('blocked','incomplete','out_of_scope') else 'unknown', response.get('reason', 'HTTP ' + str(response.get('status'))))
                results.stage_status['collection'] = 'partial'
                continue
            final_url = normalize(response['url'])
            if final_url in collected:
                continue
            content_type = response['headers'].get('content-type', '').lower()
            if 'application/pdf' in content_type or (not content_type and final_url.lower().endswith('.pdf')):
                if 'crawl' in required:
                    safe('crawl', final_url, lambda: pdf_check(response, results, facts))
                collected.add(final_url)
                continue
            if 'html' not in content_type and content_type:
                continue
            page = safe('collection', url, lambda: Page(response))
            if page is None:
                continue
            if not scope.resolved:
                target = scope.resolve(page)
                if target:
                    queue.insert(0, target)
                    results.check('collection.locale_selector', page.url, 'not_applicable', 'Selected published alternate: ' + target)
                    continue
            if not scope.accepts_document(page):
                results.check('collection.locale', page.url, 'unknown', 'Document language/market conflicts with the selected locale; excluded from analysis.')
                continue
            if not pages and not brand:
                brand = published_brand(page) or urlsplit(site).hostname
            inspect(page)
            links = [a['url'] for a in sorted(page.links, key=lambda a:not a['in_main']) if a['url'].startswith(('http://', 'https://')) and scope.allows(a['url']) and not excluded_url(a['url'])]
            queue[:] = prioritize_links([u for u in links + queue if u not in attempted and u not in collected],
                                        seen={p.purpose for p in pages},
                                        counts={kind:sum(p.purpose == kind for p in pages) for kind in {p.purpose for p in pages}})
    with collector.allowance(budget * .35, min(60, max(4, int(collector.max_requests * .3)))):
        safe('collection', site, collect)
    finish('collection')
    if pages and 'crawl' in required:
        from .discovery import link_checks
        with collector.allowance(min(10, budget * .06), 8):
            safe('crawl', site, lambda: link_checks(pages, collector, results))
    if pages and 'engagement' in required:
        with collector.allowance(budget * .10, min(12, max(2, int(collector.max_requests * .1)))):
            for page in list(pages):
                safe('engagement', page.url, lambda p=page: engagement_checks(p, results, collector))
        for page in list(collector.followup_pages.values())[:3]:
            if page.url not in collected and scope.accepts_document(page):
                inspect(page)
    if pages and 'claims' in required:
        safe('claims', site, lambda: identity_checks(pages, brand, results))
        safe('claims', site, lambda: compare_site_claims(results.claims, results))
        finish('claims')
    if pages and 'crawl' in required:
        from .discovery import content_checks
        from .structured import coverage_checks
        # Preserve inexpensive SEO evidence before browser work can time out.
        before = (len(results.findings), len(results.suggestions), len(results.checks), len(results.reviews))
        safe('crawl', site, lambda: content_checks(pages, results))
        safe('crawl', site, lambda: coverage_checks(pages, results))
        preliminary = [items[start:] for items, start in zip(
            (results.findings, results.suggestions, results.checks, results.reviews), before)]
        finish('crawl')
    if pages and 'render' in required:
        # One representative of each purpose gets a complete resource allowance first.
        selected, purposes = [], set()
        purpose_order = {'product':0,'pricing':1,'returns':2,'delivery':3,'service':4,'category':5,'homepage':6,'support':7,'informational':8,'article':9}
        for page in sorted(pages, key=lambda p:purpose_order.get(p.purpose,10)):
            if page.purpose not in purposes:
                selected.append(page); purposes.add(page.purpose)
        selected += [p for p in pages if p not in selected]
        selected = selected[:3]
        for page in pages:
            if page not in selected:
                results.check('render.selection', page.url, 'not_applicable', 'Static sample; browser budget reserved for representative page purposes.')
        results.on_progress = save
        rendered = safe('render', site, lambda: render_pages(selected, collector, results, browser))
        capabilities['headless_browser'] = bool(rendered) or any(p.rendered for p in pages)
        if capabilities['headless_browser']:
            finish('render')
        else:
            results.stage_status['render'] = 'not_run'
        from .crawl import metadata_checks, schema_checks
        for page in pages:
            for viewport, sample in page.rendered.items():
                if 'crawl' in required and sample.get('metadata_html') and sample.get('content_reliable'):
                    def rendered_metadata(p=page, sample=sample, viewport=viewport):
                        rendered_page = Page({**p.response, 'body':sample['metadata_html'].encode('utf-8')})
                        metadata_checks(rendered_page, results, 'rendered_' + viewport)
                        schema_checks(rendered_page, results)
                    safe('crawl', page.url, rendered_metadata)
            if 'engagement' in required:
                safe('engagement', page.url, lambda p=page: engagement_checks(p, results, rendered_only=True))
    if pages and 'engagement' in required:
        finish('engagement')
    if pages and 'crawl' in required:
        # Replace provisional coverage so observed injected markup can clear a
        # raw-HTML gap without discarding positive checks from other specialists.
        for items, old in zip((results.findings, results.suggestions, results.checks, results.reviews), preliminary):
            old_ids = {id(item) for item in old}
            items[:] = [item for item in items if id(item) not in old_ids]
        safe('crawl', site, lambda: content_checks(pages, results))
        safe('crawl', site, lambda: coverage_checks(pages, results))
    if pages and 'facts' in required:
        def inspect_facts():
            selected = candidates(pages, brand, facts)
            stress_tests(pages, selected, brand, results)
            results.check('facts.sample', site, 'pass' if selected else 'unknown',
                str(len(selected)) + ' evidence questions evaluated; source spans and unresolved context are retained.')
        safe('facts', site, inspect_facts)
        finish('facts')
    # Only failed execution/required observations make a component partial; optional
    # field metrics and bounded static samples do not mask successful checks.
    for stage in stages:
        if results.stage_status[stage] == 'pending':
            results.stage_status[stage] = 'not_run'
        if stage == 'render' and results.stage_status[stage] == 'sampled' and any(
            c['check_id'].startswith('render.browser') and c['status'] in ('unknown', 'not_run') for c in results.checks):
            results.stage_status[stage] = 'partial'
        if results.stage_status[stage] in ('not_run', 'partial'):
            results.check('stage.' + stage, site, 'not_run' if results.stage_status[stage] == 'not_run' else 'unknown',
                'Stage coverage is ' + results.stage_status[stage] + '; completed observations remain usable.')
    save()
    final = report()
    validate_report(final)
    return final


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Full read-only brand audit; saves one compact <company>_report.json in the current directory')
    parser.add_argument('site_url')
    parser.add_argument('--brand', help='Company name used for the report filename; otherwise use the published site name or domain')
    parser.add_argument('--pages', nargs='*', default=[])
    parser.add_argument('--facts', nargs='*', default=[])
    parser.add_argument('--facts-file', help='JSON list of question, terms, optional source_url and context dimensions')
    parser.add_argument('--country', help='One ISO country code, e.g. IN; defaults to site evidence')
    parser.add_argument('--language', help='One language tag, e.g. en or hi; defaults to site evidence')
    parser.add_argument('--max-requests', type=int, default=400, help='Shared HTTP request cap; default 400')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--budget', type=float, default=270, help='Work seconds, 1–270; supervisor reserves 20 seconds for shutdown/output')
    parser.add_argument('--max-response-mb', type=float, default=20, help='Maximum decoded body per response in decimal MB (default: 20)')
    parser.add_argument('--max-download-mb', type=float, default=100, help='Total decoded response-body budget in decimal MB (default: 100)')
    parser.add_argument('--_worker', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 1 <= args.budget <= 270:
        parser.error('--budget must be between 1 and 270 seconds')
    import math
    if any(not math.isfinite(v) or v < 0.001 for v in (args.max_response_mb, args.max_download_mb)):
        parser.error('Download limits must be finite and at least 0.001 MB')
    if args.country and args.country.lower() not in COUNTRIES:
        parser.error('--country must be an ISO two-letter country code')
    if args.language and language_tag(args.language).split('-')[0] not in LANGUAGES:
        parser.error('--language must be a supported language tag')
    if not 1 <= args.max_requests <= 2000:
        parser.error('--max-requests must be between 1 and 2000')
    try:
        normalize(args.site_url)
        for page_url in args.pages:
            normalize(page_url)
        args.fact_data = json.loads(Path(args.facts_file).read_text(encoding='utf-8-sig')) if args.facts_file else args.facts
        if not isinstance(args.fact_data, list):
            raise ValueError('Fact manifest must contain a JSON array')
        for fact in args.fact_data:
            if not isinstance(fact, str) and (not isinstance(fact, dict) or not isinstance(fact.get('question'), str) or not isinstance(fact.get('terms'), list)):
                raise ValueError('Each fact needs question and terms (array)')
            if isinstance(fact, dict):
                if not all(isinstance(term, str) and term.strip() for term in fact['terms']):
                    raise ValueError('Evidence terms must be nonempty strings')
                context = fact.get('context', {})
                if not isinstance(context, dict) or not all(isinstance(v, str) and v.strip() for v in context.values()):
                    raise ValueError('Context must map dimensions to nonempty source strings')
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(str(exc))
    return args


def atomic_json(path, report):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def main(component=None):
    import jsonschema
    args = parse_args()
    supervisor_started = time.monotonic()
    if args._worker:
        audit(args.site_url, brand=args.brand, facts=args.fact_data, extra_pages=args.pages,
              browser=not args.no_browser, budget=args.budget, country=args.country, language=args.language, max_requests=args.max_requests, checkpoint=lambda r: atomic_json(args._worker, r), component=component,
              max_response_bytes=int(args.max_response_mb * 1_000_000), max_download_bytes=int(args.max_download_mb * 1_000_000))
        return
    # One supervisor deadline covers DNS, imports, HTTP streaming, browser work and all stages.
    with tempfile.TemporaryDirectory(prefix='brand-audit-') as temp:
        checkpoint = Path(temp) / 'report.json'
        command = [sys.executable, str(Path(sys.argv[0]).resolve()), *sys.argv[1:], '--_worker', str(checkpoint)]
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
            start_new_session=os.name != 'nt')
        timed_out = False
        try:
            _, stderr = process.communicate(timeout=args.budget + 10)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=5, check=True)
                else:
                    import signal
                    os.killpg(process.pid, signal.SIGKILL)
            except (OSError, subprocess.SubprocessError):
                # The report must remain available even if process-tree cleanup fails.
                try:
                    process.kill()
                except OSError:
                    pass
            try:
                _, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                stderr = b'Worker cleanup did not complete; retained durable partial evidence.'
                if process.stderr:
                    process.stderr.close()
        try:
            report = json.loads(checkpoint.read_text(encoding='utf-8'))
            validate_report(report)
        except (OSError, ValueError, AssertionError, jsonschema.ValidationError):
            report = snapshot(args.site_url, args.brand, Collector(seconds=1), Results(), [], {}, args.budget)
            report['checks'].append({'check_id':'run.checkpoint', 'resource':args.site_url, 'status':'unknown', 'reason':'No valid worker checkpoint was available.', 'evidence_items':[]})
        if timed_out or process.returncode:
            report['checks'].append({'check_id': 'run.supervisor', 'resource': args.site_url, 'status': 'not_run',
                                     'reason': 'Global supervisor stopped the worker; report is partial.' if timed_out else stderr.decode('utf-8', 'replace')[-1000:], 'evidence_items': []})
            finished = set(report['run_metadata'].get('stages_completed', []))
            for stage in ('collection', 'crawl', 'render', 'facts', 'claims', 'engagement'):
                if stage in finished:
                    continue
                report['checks'].append({'check_id': 'stage.' + stage, 'resource': args.site_url, 'status': 'unknown',
                                         'reason': 'Worker interrupted; consult completed per-resource checks.', 'evidence_items': []})
        report['run_metadata']['elapsed_seconds'] = round(time.monotonic() - supervisor_started, 3)
        validate_report(report)
        from .reporting import owner_report as business_report, report_filename
        output = report_filename(args.site_url, args.brand or report.get('brand'))
        report = business_report(report, component)
        import jsonschema
        jsonschema.validate(report, json.loads((ROOT / 'skills/audit-orchestrator/references/owner.schema.json').read_text(encoding='utf-8')))
        assert report['summary']['total_findings'] == len(report['findings'])
        atomic_json(output, report)
        print('Saved ' + output + ' (' + str(len(report['findings'])) + ' findings, ' + str(report['improvements_summary']['total_improvements']) + ' improvements).')


if __name__ == '__main__':
    main()
