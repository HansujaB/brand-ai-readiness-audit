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
from .freshness import check_freshness, check_article_dates, compare_product_claims, extract_product_claims, prioritize_links
from .identity import identity_checks

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


def snapshot(site, brand, depth, collector, results, pages, capabilities, work_budget):
    findings = merge_findings(results.findings)
    checks = list({json.dumps(c, sort_keys=True): c for c in results.checks}.values())
    return {'site': site, 'brand': brand, 'audited_at': utcnow(),
        'run_metadata': {'depth': depth, 'pages_audited': [p.url for p in pages],
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
        'visitor_journeys': results.journeys, 'local_rewrite_tests': results.rewrites}


def audit(site, brand=None, depth='standard', facts=None, extra_pages=None, external=None, browser=True,
          budget=270, collector=None, checkpoint=None, component=None, max_response_bytes=20_000_000, max_download_bytes=100_000_000):
    site = normalize(site)
    collector = collector or Collector(seconds=budget, max_response_bytes=max_response_bytes, max_download_bytes=max_download_bytes)
    results, pages = Results(), []
    brand = brand or urlsplit(site).hostname
    capabilities = {'python_execution': True, 'headless_browser': False, 'web_search': False, 'external_sample': False}
    stages = ['collection', 'crawl', 'render', 'facts', 'claims', 'external', 'engagement']
    completed = set()
    results.completed_stages = []
    report = lambda: snapshot(site, brand, depth, collector, results, pages, capabilities, budget)
    def save():
        results.completed_stages = sorted(completed)
        if checkpoint:
            checkpoint(report())
    save()
    required = {'collection'}
    if component in (None, 'crawl'):
        required.update(('crawl','render','facts'))
    if component in (None, 'freshness'):
        required.update(('claims','external'))
        if facts:
            required.add('facts')
    if component in (None, 'engagement'):
        required.update(('engagement','render'))
    results.stage_status = {stage: 'pending' if stage in required else 'not_applicable' for stage in stages}
    def safe(stage, url, operation):
        try:
            value = operation()
            save()
            return value
        except BudgetExceeded as exc:
            results.check(stage + '.budget', url, 'not_run', str(exc))
        except Exception as exc:
            results.check(stage + '.internal_error', url, 'unknown', type(exc).__name__ + ': ' + str(exc)[:300])
        results.stage_status[stage] = 'partial'
        save()
        return None
    def finish(stage):
        completed.add(stage)
        if results.stage_status[stage] != 'partial':
            results.stage_status[stage] = 'sampled'
        save()
    limit = {'quick': 1, 'standard': 5, 'deep': 9}[depth]
    queue, attempted, collected = [site] + list(extra_pages or []), set(), set()
    accepted_origins = {origin(site)}
    discovery_done = False
    def discover_sitemaps(base):
        sitemap_queue = collector.policy(base).sitemaps[:2] or [origin(base) + '/sitemap.xml']
        visited = set()
        while sitemap_queue and len(visited) < 4:
            raw = sitemap_queue.pop(0)
            try:
                url = normalize(raw)
            except (ValueError, TypeError):
                results.check('access.sitemap', str(raw), 'unknown', 'Invalid sitemap URL; skipped.')
                continue
            if url in visited or origin(url) not in accepted_origins:
                continue
            visited.add(url)
            response = collector.fetch(url)
            if response['state'] != 'ok':
                results.check('access.sitemap', url, 'not_applicable' if response.get('status') in (404,410) else 'unknown', 'Sitemap unavailable; normal links remain valid discovery paths.')
                continue
            try:
                xml = ElementTree.fromstring(response['body'])
                tag = xml.tag.split('}')[-1]
                if tag not in ('urlset','sitemapindex'):
                    raise ValueError('Expected urlset or sitemapindex root')
                locs = [e.text.strip() for e in xml.iter() if e.tag.split('}')[-1] == 'loc' and e.text and e.text.strip()]
                if tag == 'sitemapindex':
                    sitemap_queue.extend(locs[:4])
                else:
                    queue.extend(locs[:limit * 10])
                results.check('access.sitemap', url, 'pass', 'Parsed ' + tag + '; listed page URLs enter the bounded discovery queue.')
            except (ElementTree.ParseError, ValueError) as exc:
                results.finding('access.sitemap_invalid', url, 'Published sitemap is malformed', str(exc),
                    'Repair the sitemap XML and its document type.', 'Validate this sitemap and any child sitemap.', severity='low')
            save()
    def collect():
        nonlocal discovery_done
        while queue and len(collected) < limit and len(attempted) < limit * 4:
            collector.remaining()
            raw = queue.pop(0)
            try:
                url = normalize(raw)
            except (ValueError, TypeError) as exc:
                results.check('collection.invalid_link', str(raw), 'unknown', str(exc))
                continue
            if url in attempted or url in collected or origin(url) not in accepted_origins or excluded_url(url):
                continue
            attempted.add(url)
            response = safe('collection', url, lambda: collector.fetch(url))
            if not response:
                continue
            if response['state'] != 'ok':
                results.check('access.fetch', url, 'not_run' if response['state'] in ('blocked','incomplete') else 'unknown', response.get('reason', 'HTTP ' + str(response.get('status'))))
                results.stage_status['collection'] = 'partial'
                save()
                continue
            final_url = normalize(response['url'])
            if url == site:
                accepted_origins.add(origin(final_url))
            if final_url in collected or origin(final_url) not in accepted_origins:
                continue
            content_type = response['headers'].get('content-type', '').lower()
            if 'application/pdf' in content_type or (not content_type and final_url.lower().endswith('.pdf')):
                safe('crawl', final_url, lambda: pdf_check(response, results, facts))
                collected.add(final_url)
                continue
            if 'html' not in content_type and content_type:
                results.check('collection.content_type', url, 'not_applicable', 'Unsupported media type; no visibility conclusion.')
                continue
            page = safe('collection', url, lambda: Page(response))
            if page is None:
                continue
            pages.append(page)
            collected.add(final_url)
            results.check('access.fetch', final_url, 'pass', 'Public HTML page collected.', [evidence(final_url, 'HTTP ' + str(response['status']), 'http')])
            # Persist non-network diagnostics immediately, before supplementary discovery/rendering.
            if 'crawl' in required:
                safe('crawl', final_url, lambda: crawl_checks(page, results, collector))
            if 'claims' in required:
                def claims_for_page():
                    results.claims.extend(extract_product_claims(page, brand))
                    check_freshness(page, results)
                    check_article_dates(page, results)
                safe('claims', final_url, claims_for_page)
            if 'engagement' in required:
                safe('engagement', final_url, lambda: engagement_checks(page, results))
            queue.extend(prioritize_links([a['url'] for a in page.links if a['url'].startswith(('http://','https://'))]))
            save()
            if not discovery_done and depth != 'quick':
                discovery_done = True
                with collector.allowance(min(8, budget * .08), 5):
                    safe('collection', final_url, lambda: discover_sitemaps(final_url))
    with collector.allowance(budget * .35, max(4, int(collector.max_requests * .4))):
        safe('collection', site, collect)
    finish('collection')
    if pages:
        for stage in ('crawl','claims','engagement'):
            if stage in required:
                finish(stage)
    if pages and 'engagement' in required:
        with collector.allowance(budget * .12, max(2, int(collector.max_requests * .12))):
            for page in pages:
                safe('engagement', page.url, lambda p=page: engagement_checks(p, results, collector))
    external_pages = []
    if pages and 'external' in required:
        if external and depth != 'quick':
            with collector.allowance(budget * .12, max(2, int(collector.max_requests * .12))):
                for source in external[:{'standard':5,'deep':10}[depth]]:
                    def external_source():
                        response = collector.fetch(source['url'])
                        if response['state'] != 'ok' or 'html' not in response.get('headers', {}).get('content-type',''):
                            results.check('external.source', source['url'], 'unknown', 'No complete HTML evidence from this source.')
                            results.stage_status['external'] = 'partial'
                            return
                        page = Page(response)
                        external_pages.append(page)
                        annotation = dict(source)
                        if origin(page.url) in accepted_origins:
                            annotation['ownership'] = 'brand'
                        results.claims.extend(extract_product_claims(page, annotation.get('entity', brand), annotation))
                        capabilities['external_sample'] = True
                        results.check('external.source', source['url'], 'pass', 'Imported source inspected; ownership annotations are researcher supplied.')
                    safe('external', source.get('url', ''), external_source)
            finish('external')
        else:
            results.stage_status['external'] = 'not_run'
            results.check('external.search', site, 'not_run', 'No external source sample inspected: quick depth or no source manifest supplied.')
        safe('claims', site, lambda: identity_checks(pages, external_pages, brand, results))
        safe('claims', site, lambda: compare_product_claims(results.claims, results))
    if pages and 'render' in required:
        # Unused earlier allowances are available to rendering. Checkpoint each viewport.
        results.on_progress = save
        rendered = safe('render', site, lambda: render_pages(pages, collector, results, browser))
        capabilities['headless_browser'] = bool(rendered) or any(p.rendered for p in pages)
        if capabilities['headless_browser']:
            finish('render')
        else:
            results.stage_status['render'] = 'not_run'
        from .crawl import metadata_checks, schema_checks
        for page in pages:
            if 'crawl' in required:
                for viewport, sample in page.rendered.items():
                    if sample.get('metadata_html') and sample.get('content_reliable', sample.get('reliable')):
                        def rendered_metadata(p=page, sample=sample, viewport=viewport):
                            rendered_page = Page({**p.response, 'body':sample['metadata_html'].encode('utf-8')})
                            metadata_checks(rendered_page, results, 'rendered_' + viewport)
                            schema_checks(rendered_page, results)
                        safe('crawl', page.url, rendered_metadata)
            if 'engagement' in required:
                safe('engagement', page.url, lambda p=page: engagement_checks(p, results, rendered_only=True))
    if pages and 'facts' in required:
        def inspect_facts():
            selected = candidates(pages, brand, facts)
            stress_tests(pages, selected, brand, results)
            results.check('facts.sample', site, 'unknown' if not selected or any(x['status'] == 'unknown' for x in results.fact_tests) else 'pass',
                str(len(selected)) + ' bounded evidence questions; term preservation does not establish semantic answer correctness.')
        safe('facts', site, inspect_facts)
        finish('facts')
    prefixes = {'collection':('collection.','access.fetch','access.sitemap'), 'crawl':('access.','schema.','media.'), 'render':('render.','performance.lab.'), 'facts':('facts.',), 'claims':('claims.','freshness.','identity.'), 'external':('external.',), 'engagement':('journey.',)}
    for stage in stages:
        if results.stage_status[stage] == 'sampled' and any(c['status'] in ('unknown','not_run') and c['check_id'].startswith(prefixes[stage]) for c in results.checks):
            results.stage_status[stage] = 'partial'
        status = results.stage_status[stage]
        if status == 'pending':
            status = results.stage_status[stage] = 'not_run'
        if status in ('not_run','partial'):
            results.check('stage.' + stage, site, 'not_run' if status == 'not_run' else 'unknown', 'Stage coverage is ' + status + '; consult completed per-resource checks.')
    save()
    final = report()
    validate_report(final)
    if checkpoint:
        checkpoint(final)
    return final


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Evidence-driven, read-only brand audit')
    parser.add_argument('site_url')
    parser.add_argument('--brand')
    parser.add_argument('--depth', choices=['quick', 'standard', 'deep'], default='standard')
    parser.add_argument('--pages', nargs='*', default=[])
    parser.add_argument('--facts', nargs='*', default=[])
    parser.add_argument('--facts-file', help='JSON list of question, terms, optional source_url and context dimensions')
    parser.add_argument('--search-results', help='JSON list of source URL, ownership, group, optional entity; imported search sample')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--budget', type=float, default=270, help='Work seconds, 1–270; supervisor reserves 20 seconds for shutdown/output')
    parser.add_argument('--max-response-mb', type=float, default=20, help='Maximum decoded body per response in decimal MB (default: 20)')
    parser.add_argument('--max-download-mb', type=float, default=100, help='Total decoded response-body budget in decimal MB (default: 100)')
    parser.add_argument('--output', help='Optional JSON output path')
    parser.add_argument('--diagnostics-output', help='Optional detailed evidence JSON; freshness output is compact')
    parser.add_argument('--_worker', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 1 <= args.budget <= 270:
        parser.error('--budget must be between 1 and 270 seconds')
    import math
    if any(not math.isfinite(v) or v < 0.001 for v in (args.max_response_mb, args.max_download_mb)):
        parser.error('Download limits must be finite and at least 0.001 MB')
    try:
        normalize(args.site_url)
        for page_url in args.pages:
            normalize(page_url)
        args.fact_data = json.loads(Path(args.facts_file).read_text(encoding='utf-8-sig')) if args.facts_file else args.facts
        args.external_data = json.loads(Path(args.search_results).read_text(encoding='utf-8-sig')) if args.search_results else []
        if not isinstance(args.fact_data, list) or not isinstance(args.external_data, list):
            raise ValueError('Fact and search manifests must contain JSON arrays')
        for fact in args.fact_data:
            if not isinstance(fact, str) and (not isinstance(fact, dict) or not isinstance(fact.get('question'), str) or not isinstance(fact.get('terms'), list)):
                raise ValueError('Each fact needs question and terms (array)')
            if isinstance(fact, dict):
                if not all(isinstance(term, str) and term.strip() for term in fact['terms']):
                    raise ValueError('Evidence terms must be nonempty strings')
                context = fact.get('context', {})
                if not isinstance(context, dict) or not all(isinstance(v, str) and v.strip() for v in context.values()):
                    raise ValueError('Context must map dimensions to nonempty source strings')
        for source in args.external_data:
            if not isinstance(source, dict) or not isinstance(source.get('url'), str):
                raise ValueError('Each source must be an object with a URL string')
            normalize(source['url'])
            if any(key in source and not isinstance(source[key], str) for key in ('entity', 'group')):
                raise ValueError('Source entity and group must be strings')
            if source.get('ownership', 'unknown') not in ('brand', 'independent', 'unknown'):
                raise ValueError('Source ownership must be brand, independent or unknown')
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
        audit(args.site_url, args.brand, args.depth, args.fact_data, args.pages, args.external_data,
              not args.no_browser, args.budget, checkpoint=lambda r: atomic_json(args._worker, r), component=component,
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
            report = snapshot(args.site_url, args.brand, args.depth, Collector(seconds=1), Results(), [], {}, args.budget)
            report['checks'].append({'check_id':'run.checkpoint', 'resource':args.site_url, 'status':'unknown', 'reason':'No valid worker checkpoint was available.', 'evidence_items':[]})
        if timed_out or process.returncode:
            report['checks'].append({'check_id': 'run.supervisor', 'resource': args.site_url, 'status': 'not_run',
                                     'reason': 'Global supervisor stopped the worker; report is partial.' if timed_out else stderr.decode('utf-8', 'replace')[-1000:], 'evidence_items': []})
            finished = set(report['run_metadata'].get('stages_completed', []))
            for stage in ('collection', 'crawl', 'render', 'facts', 'claims', 'external', 'engagement'):
                if stage in finished:
                    continue
                report['checks'].append({'check_id': 'stage.' + stage, 'resource': args.site_url, 'status': 'unknown',
                                         'reason': 'Worker interrupted; consult completed per-resource checks.', 'evidence_items': []})
        report['run_metadata']['elapsed_seconds'] = round(time.monotonic() - supervisor_started, 3)
        validate_report(report)
        if args.diagnostics_output:
            atomic_json(args.diagnostics_output, report)
        from .reporting import owner_report as business_report
        report = business_report(report, component)
        import jsonschema
        jsonschema.validate(report, json.loads((ROOT / 'skills/audit-orchestrator/references/owner.schema.json').read_text(encoding='utf-8')))
        assert report['summary']['total_findings'] == len(report['findings'])
        if args.output:
            atomic_json(args.output, report)
        print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
