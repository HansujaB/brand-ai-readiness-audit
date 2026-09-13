"""Anonymous browser lab observations; all HTTP requests go through Collector."""
import json
import base64
import re
import os
import time
from pathlib import Path
from .collection import BudgetExceeded, normalize
from .diagnostics import MONEY, norm, evidence

OBSERVE = r'''(options = {}) => {
 const viewportWidth=options.width||document.documentElement.clientWidth;
 const roots=[document];
 for(let i=0;i<roots.length;i++) for(const e of roots[i].querySelectorAll('*')) if(e.shadowRoot) roots.push(e.shadowRoot);
 const all = selector => roots.flatMap(root=>[...root.querySelectorAll(selector)]);
 const main=document.querySelector('main,article,[role=main]')||document.body;
 const visible=e=>{let n=e; while(n&&n.nodeType===1){const s=getComputedStyle(n); if(s.display==='none'||s.visibility==='hidden'||Number(s.opacity)===0||n.hidden||n.inert)return false;n=n.parentElement||n.getRootNode()?.host;} const r=e.getBoundingClientRect();return r.width>0&&r.height>0;};
 const locator=e=>{if(!e)return null; if(e.id)return '#'+CSS.escape(e.id);if(e.getRootNode()?.host)return locator(e.getRootNode().host)+' >>> '+e.tagName.toLowerCase();let parts=[];while(e&&e.nodeType===1&&parts.length<5){const siblings=e.parentElement?[...e.parentElement.children].filter(n=>n.tagName===e.tagName):[];parts.unshift(e.tagName.toLowerCase()+':nth-of-type('+(siblings.indexOf(e)+1)+')');e=e.parentElement;}return parts.join(' > ');};
 const rect=e=>{const r=e.getBoundingClientRect();return {x:Math.round(r.x),y:Math.round(r.y),width:Math.round(r.width),height:Math.round(r.height)};};
 const hitInfo=e=>{const r=e.getBoundingClientRect(),left=Math.max(0,r.left),right=Math.min(viewportWidth,r.right),top=Math.max(0,r.top),bottom=Math.min(innerHeight,r.bottom);const inView=right>left&&bottom>top;let hit=inView?document.elementFromPoint((left+right)/2,(top+bottom)/2):null;while(hit?.shadowRoot){const inner=hit.shadowRoot.elementFromPoint((left+right)/2,(top+bottom)/2);if(!inner||inner===hit)break;hit=inner;}return {in_viewport:inView,obstructed:inView&&!(hit===e||e.contains(hit)),blocker:locator(hit)};};
 const name=e=>{const labelled=(e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>e.getRootNode().getElementById?.(id)?.textContent||'').join(' ').trim();return (labelled||e.getAttribute('aria-label')||[...(e.labels||[])].map(l=>l.innerText).join(' ')||e.innerText||e.value||e.querySelector('img')?.alt||e.title||'').trim();};
 const patterns={product:/cart|buy|purchase|size|variant|return|refund|spec|खरीद|वापसी/i,pricing:/plan|start|try|subscribe|compare|योजना/i,service:/contact|enquir|book|संपर्क/i,documentation:/search|guide|next|example|download/i,article:/read|related|source|next/i,homepage:/shop|browse|explore|product|service|catalog|learn/i};
 const nodes=all('a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=searchbox]');
 const actions=nodes.filter(visible).map(e=>{const label=name(e),hit=hitInfo(e);return {name:label,href:e.href||null,role:e.getAttribute('role')||e.tagName.toLowerCase(),locator:locator(e),rect:rect(e),...hit,enabled:!e.matches(':disabled')&&!e.closest('[aria-disabled=true]'),relevant:(patterns[options.purpose]||/price|plan|buy|cart|contact|return|spec|next|खरीद|वापसी/i).test(label+' '+(e.getAttribute('href')||''))};});
 const blocks=[...main.querySelectorAll('p,li,tr,section,h1,h2,h3')].filter(visible);
 const content=blocks.map(e=>({text:e.innerText,locator:locator(e),rect:rect(e),...hitInfo(e)})).filter(b=>b.text&&b.text.length<3000);
 const overflow_elements=blocks.filter(e=>{const r=e.getBoundingClientRect();return r.right>viewportWidth+2&&!e.closest('table,pre,[role=grid],[role=table]')&&r.width>viewportWidth&&e.innerText.length>40;}).map(e=>({locator:locator(e),text:e.innerText,rect:rect(e)}));
 const n=performance.getEntriesByType('navigation')[0];
 return {text:main?.innerText||'',actions,content,blocks:content.map(b=>b.text),overflow:overflow_elements.length>0,overflow_elements,
   metrics:{kind:'single_anonymous_lab_observation',navigation_ms:n?.duration||null,fcp_ms:performance.getEntriesByName('first-contentful-paint')[0]?.startTime||null,lcp_ms:window.__auditVitals?.lcp||null,cls_observed:window.__auditVitals?.max||0,inp_ms:null},
   unsupported_frames:all('iframe').filter(visible).length,metadata_html:[...document.querySelectorAll('base,meta,link[rel],script[type="application/ld+json"]')].map(e=>e.outerHTML).join(''),scroll_y:scrollY};
}'''
INIT = r'''window.__auditVitals={lcp:null,max:0,sum:0,start:0,last:0};
try{new PerformanceObserver(l=>{for(const e of l.getEntries())window.__auditVitals.lcp=e.startTime;}).observe({type:'largest-contentful-paint',buffered:true});}catch(e){}
try{new PerformanceObserver(l=>{for(const e of l.getEntries()){if(e.hadRecentInput)continue;const v=window.__auditVitals;if(e.startTime-v.last>1000||e.startTime-v.start>5000){v.start=e.startTime;v.sum=0;}v.sum+=e.value;v.last=e.startTime;v.max=Math.max(v.max,v.sum);}}).observe({type:'layout-shift',buffered:true});}catch(e){}
'''


def render_pages(pages, collector, results, enabled=True):
    if not enabled:
        for page in pages:
            results.check('render.browser', page.url, 'not_run', 'Browser disabled by run configuration.')
        return False
    local_browsers = Path(__file__).resolve().parents[1] / '.browsers'
    if local_browsers.is_dir():
        os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(local_browsers))
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        for page in pages:
            results.check('render.browser', page.url, 'not_run', 'Playwright is not installed.')
        return False
    used = False
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(timeout=min(15000, collector.remaining()*1000))
            try:
                for page in pages:
                    if not collector.allows_origin(page.url):
                        results.check('render.browser', page.url, 'not_run', 'Outside the supplied URL origin.')
                        continue
                    for viewport, size in [('desktop', {'width': 1365, 'height': 768}), ('mobile', {'width': 390, 'height': 844})]:
                        if collector.remaining() < 5:
                            results.check('render.browser.' + viewport, page.url, 'not_run', 'Browser allowance exhausted; static engagement evidence retained.')
                            continue
                        started_requests, sample_started = len(collector.log), time.monotonic()
                        request_allowance = min(140, collector.max_requests - started_requests)
                        time_allowance = min(35, max(2, collector.remaining() - 5))
                        context = browser.new_context(viewport=size, is_mobile=viewport == 'mobile', has_touch=viewport == 'mobile', user_agent=playwright.devices['Pixel 7' if viewport == 'mobile' else 'Desktop Chrome']['user_agent'], device_scale_factor=2 if viewport == 'mobile' else 1, service_workers='block', accept_downloads=False)
                        # Chromium stays offline: every permitted HTTP response is supplied by
                        # Collector. Targets not attached to this CDP session fail closed.
                        context.set_offline(True)
                        context.add_init_script(INIT)
                        context.add_init_script("Object.defineProperty(navigator, 'onLine', {get:()=>true});")
                        tab = context.new_page()
                        session = context.new_cdp_session(tab)
                        main_frame_id = session.send('Page.getFrameTree')['frameTree']['frame']['id']
                        blocked, errors = [], []
                        def intercept(event):
                            request = event['request']
                            url = request['url']
                            kind = event.get('resourceType', 'Other').lower()
                            request_id = event['requestId']
                            def abort(reason):
                                blocked.append({'url':url, 'resource_type':kind, 'reason':reason,
                                                'main_frame':event.get('frameId', main_frame_id) == main_frame_id})
                                session.send('Fetch.failRequest', {'requestId':request_id, 'errorReason':'BlockedByClient'})
                            try:
                                if request['method'] != 'GET' or not url.startswith(('http://', 'https://')):
                                    abort('Only anonymous HTTP GET is permitted')
                                    return
                                if not collector.allows_origin(url):
                                    abort('Outside the supplied URL origin')
                                    return
                                cached = normalize(url) in collector.cache or normalize(url) in collector.redirect_cache
                                if (not cached and len(collector.log) >= min(collector.max_requests, started_requests + request_allowance)) or time.monotonic() - sample_started > time_allowance:
                                    abort('Per-viewport browser allowance exhausted')
                                    return
                                response = collector.fetch(url, purpose='page' if kind == 'document' else 'asset', follow_redirects=False)
                                if response['state'] not in ('ok', 'http_error'):
                                    abort(response.get('reason', response['state']))
                                    return
                                headers = [{'name':k, 'value':', '.join(v) if isinstance(v,list) else str(v)} for k,v in response['headers'].items() if k not in
                                    ('content-encoding','content-length','transfer-encoding','set-cookie','connection')]
                                session.send('Fetch.fulfillRequest', {'requestId':request_id, 'responseCode':response['status'],
                                    'responseHeaders':headers, 'body':base64.b64encode(response['body']).decode('ascii')})
                            except Exception as exc:
                                try:
                                    abort(str(exc))
                                except Exception:
                                    errors.append('Browser interception closed before response delivery.')
                        session.on('Fetch.requestPaused', intercept)
                        session.send('Fetch.enable', {'patterns':[{'urlPattern':'*','requestStage':'Request'}]})
                        if hasattr(context, 'route_web_socket'):
                            context.route_web_socket('**/*', lambda ws: ws.close())
                        def failed_request(request):
                            try:
                                is_main = request.frame == tab.main_frame
                            except Exception:
                                is_main = False
                            blocked.append({'url':request.url, 'resource_type':request.resource_type,
                                'reason':str(request.failure), 'main_frame':is_main})
                        tab.on('requestfailed', failed_request)
                        tab.on('pageerror', lambda error: errors.append(str(error)))
                        try:
                            try:
                                tab.goto(page.url, wait_until='commit', timeout=min(15000, collector.remaining()*1000))
                            except Exception as exc:
                                results.check('render.navigation.' + viewport, page.url, 'unknown',
                                    'Navigation did not finish normally; attempting to retain observed DOM evidence: ' + str(exc)[:200])
                            tab.wait_for_function('document.body !== null', timeout=min(5000, collector.remaining()*1000))
                            from .engagement import page_purpose
                            options = {'purpose':page_purpose(page), 'width':size['width']}
                            samples, stable, previous, consecutive = [], False, None, 0
                            current = tab.evaluate(OBSERVE, options)
                            for _ in range(8):
                                if collector.remaining() < 5:
                                    break
                                tab.wait_for_timeout(300)
                                current = tab.evaluate(OBSERVE, options)
                                signature = current['text']
                                consecutive = consecutive + 1 if signature == previous else 0
                                previous = signature
                                if consecutive >= 3:
                                    stable = True
                                    break
                            sample = current
                            samples.append(sample)
                            for position in (size['height'] * .7, size['height'] * 1.4):
                                tab.evaluate('(y)=>window.scrollTo(0,y)', position)
                                tab.wait_for_timeout(150)
                                samples.append(tab.evaluate(OBSERVE, options))
                            tab.evaluate('window.scrollTo(0,0)')
                            sample['keyboard_focus'] = []
                            for _ in range(4):
                                tab.keyboard.press('Tab')
                                focused = tab.evaluate('document.activeElement?.tagName')
                                if focused and focused not in ('BODY', 'HTML'):
                                    sample['keyboard_focus'].append(focused)
                            sample['disclosures'] = []
                            for summary in tab.locator('details > summary').all()[:2]:
                                if summary.is_visible():
                                    try:
                                        summary.click(timeout=1000)
                                        sample['disclosures'].append({'control':summary.inner_text(), 'status':'observed'})
                                        samples.append(tab.evaluate(OBSERVE, options))
                                    except Exception as exc:
                                        sample['disclosures'].append({'status':'unknown', 'reason':str(exc)[:200]})
                            for toggle in tab.locator('button[aria-expanded][aria-controls]').all()[:2]:
                                label = toggle.get_attribute('aria-label') or toggle.inner_text()
                                if toggle.is_visible() and re.search(r'menu|navigation', label, re.I) and not toggle.evaluate('(e)=>!!e.closest("form")'):
                                    before = toggle.get_attribute('aria-expanded')
                                    try:
                                        toggle.click(timeout=1000)
                                        after = toggle.get_attribute('aria-expanded')
                                        sample['disclosures'].append({'control':label,'before':before,'after':after, 'status':'observed'})
                                        if before != after:
                                            toggle.click(timeout=1000)
                                    except Exception as exc:
                                        sample['disclosures'].append({'control':label,'status':'unknown','reason':str(exc)[:200]})
                            for field, key in (('actions','locator'), ('content','locator'), ('overflow_elements','locator')):
                                merged = {}
                                for state in samples:
                                    for item in state[field]:
                                        if item[key] not in merged or item.get('in_viewport'):
                                            merged[item[key]] = item
                                sample[field] = list(merged.values())
                            failed_types = {b.get('resource_type') for b in blocked if b.get('main_frame', True)}
                            sample['content_reliable'] = stable and 'document' not in failed_types
                            sample['visual_reliable'] = sample['content_reliable'] and not failed_types.intersection(('stylesheet', 'font'))
                            sample['absence_reliable'] = sample['visual_reliable'] and not failed_types.intersection(('script','xhr','fetch')) and not errors and not sample['unsupported_frames']
                            sample['interaction_reliable'] = sample['absence_reliable']
                            sample['reliable'] = sample['absence_reliable']
                            sample['stable'] = stable
                            if sample['unsupported_frames']:
                                results.check('render.frames.' + viewport, page.url, 'unknown', 'Visible iframe contents were not inspected; main-document observations retain their own scope.')
                            sample['observation_scope'] = 'Initial viewport, two scroll positions, four Tab presses and up to two native disclosures; instrumented anonymous network.'
                            sample['blocked_requests'], sample['request_errors'] = blocked, errors
                            sample['substantive_additions'] = [b for b in sample['blocks'] if norm(b) not in norm(page.accessible_text)]
                            page.rendered[viewport] = sample
                            used = True
                            complete = sample['reliable']
                            results.check('render.substantive_content.' + viewport, page.url, 'unknown' if sample['substantive_additions'] or not complete else 'pass',
                                          'Added substantive blocks require relevance review.' if sample['substantive_additions'] else 'No substantive block additions observed.',
                                          [evidence(page.url, b, 'rendered_' + viewport) for b in sample['substantive_additions'][:5]])
                            results.check('render.browser.' + viewport, page.url, 'pass' if complete else 'unknown',
                                          'Anonymous fixed viewport sampled.' if complete else 'Main-document sample is unstable or essential resources were unavailable; inspect request evidence.')
                            if getattr(results, 'on_progress', None):
                                results.on_progress()
                            raw = norm(page.accessible_text)
                            added = [b for b in sample['blocks'] if norm(b) not in raw and MONEY.search(b)]
                            missing_prices = [p for p in MONEY.findall(sample['text']) if norm(p) not in raw]
                            if missing_prices and complete:
                                results.check('render.essential_fact.' + viewport, page.url, 'unknown',
                                    'Price tokens differ between raw and rendered text. Product identity and essentiality require a supplied fact question.',
                                    [evidence(page.url, '; '.join(added) or '; '.join(missing_prices), 'rendered_' + viewport)])
                            else:
                                results.check('render.essential_fact.' + viewport, page.url, 'pass' if complete else 'unknown',
                                              'No rendered price absent from raw text in this sample; other fact types need supplied questions.')
                            results.check('performance.lab.' + viewport, page.url, 'pass' if complete else 'unknown',
                                'Lab observation with audited/cached request delivery; not representative network performance or field Core Web Vitals. No interaction was performed; INP is unavailable.',
                                [evidence(page.url, json.dumps(sample['metrics']), 'browser_lab')])
                        except BudgetExceeded:
                            raise
                        except Exception as exc:
                            results.check('render.browser.' + viewport, page.url, 'unknown', str(exc))
                        finally:
                            context.close()
            finally:
                browser.close()
    except BudgetExceeded:
        raise
    except Exception as exc:
        for page in pages:
            if not page.rendered:
                results.check('render.browser', page.url, 'not_run', 'Browser launch unavailable: ' + str(exc)[:300])
    return used
