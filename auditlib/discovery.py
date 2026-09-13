"""Search metadata, readable content and bounded internal discovery checks."""
from collections import defaultdict
import re
from urllib.parse import urljoin, urlsplit

from .collection import BudgetExceeded, excluded_url, normalize
from .crawl import directives
from .diagnostics import Page, evidence, norm


def canonical(page):
    links = page.soup.select('link[rel="canonical"][href]')
    if len(links) == 1:
        try:
            return normalize(urljoin(page.base_url, links[0]['href']))
        except ValueError:
            pass
    return page.url


def noindex(page):
    records = []
    for meta in page.soup.select('meta[name][content]'):
        if meta['name'].lower() in ('robots', 'googlebot', 'bingbot'):
            records.extend(directives(meta['content'], meta['name'].lower()))
    header = page.response.get('headers', {}).get('x-robots-tag', [])
    for line in header if isinstance(header, list) else [header]:
        records.extend(directives(line))
    return any(scope in ('*','robots','googlebot','bingbot') and key in ('noindex','none') for scope,key,_ in records)


def content_checks(pages, results):
    titles, descriptions = defaultdict(list), defaultdict(list)
    for page in pages:
        if noindex(page) or not page.main_text.strip():
            continue
        # Use complete document evidence; tiny unstructured responses may be
        # challenges or fragments, not the site's intended page template.
        if not page.soup.head and len(page.main_text) < 40:
            continue
        title_nodes = page.soup.find_all('title')
        title = ' '.join(n.get_text(' ', strip=True) for n in title_nodes).strip()
        if not title:
            results.finding('seo.title_missing', page.url, 'Pages are missing a search title',
                'The initial HTML has no non-empty title element.',
                'Give each affected page a descriptive title that identifies its product, service or topic. Include the business name where useful and avoid repeating one generic title across different pages.',
                'Inspect the page source and confirm that each affected URL has one accurate, descriptive title.')
        elif len(set(norm(n.get_text(' ', strip=True)) for n in title_nodes)) > 1:
            results.finding('seo.title_conflict', page.url, 'Pages publish conflicting search titles', title,
                'Remove duplicate title generators from the page template. Publish one title that accurately describes the page.',
                'Confirm that the page source contains one intended title.')
        else:
            titles[norm(title)].append(page)
        meta = page.soup.select_one('meta[name="description" i]')
        description = meta.get('content','').strip() if meta else ''
        if description:
            descriptions[norm(description)].append(page)
        else:
            results.suggest('seo.description_missing', page.url,
                'No non-empty meta description is published in the initial HTML.',
                'Write a page-specific search description explaining the offering and its useful distinguishing detail. Keep it consistent with the page; search engines may choose another snippet.',
                'Confirm that the source has one relevant description for this page.', priority='low')
        alternates = defaultdict(set)
        for alternate in page.soup.select('link[hreflang][href]'):
            alternates[alternate['hreflang'].lower()].add(urljoin(page.base_url, alternate['href']))
        conflicts = [tag for tag, targets in alternates.items() if len(targets) > 1]
        if conflicts:
            results.finding('seo.hreflang_conflict', page.url, 'Language declarations point to competing pages',
                'The same hreflang value declares multiple destinations: ' + ', '.join(sorted(conflicts)) + '.',
                'Choose the intended page for each declared language and country combination. Remove competing alternate declarations from the template.',
                'Confirm that each hreflang value has one intended destination; inspect only destinations within the audit scope.', severity='low')
        main = page.visible.select_one('main,article,[role="main"]') or page.visible
        if not main.find(re.compile('^h[1-6]$')):
            results.suggest('content.headings', page.url,
                'The collected main content has no semantic section headings.',
                'Use a descriptive main heading and section headings for the important visitor questions. Keep the answer, units and applicable conditions together under each heading.',
                'Read the heading outline and confirm that each section clearly identifies its subject.', priority='medium')
        unnamed = []
        for link in main.select('a[href]'):
            if link.get_text(' ', strip=True) or link.get('aria-label') or link.get('title'):
                continue
            labelled = link.get('aria-labelledby','').split()
            if any(page.visible.find(id=i) and page.visible.find(id=i).get_text(strip=True) for i in labelled):
                continue
            images = link.find_all('img')
            if images and not any(img.get('alt','').strip() for img in images):
                unnamed.append(link['href'])
        if unnamed:
            results.finding('content.image_link_name', page.url, 'Image links have no text alternative',
                f'{len(unnamed)} main-content image links have no link text, image alternative or accessible label.',
                'Give each linked image a meaningful alternative or give the link a descriptive accessible name. Describe the destination or product rather than using a filename.',
                'Check that each affected image link has a clear name when images are unavailable.', severity='low')
        missing_alt = [img for img in main.select('img:not([alt])') if img.get('role') not in ('presentation','none')
                       and not img.get('aria-label') and not img.get('aria-labelledby')]
        if missing_alt:
            results.suggest('content.image_alternatives', page.url,
                f'{len(missing_alt)} main-content images omit an alt attribute; their role needs review.',
                'Describe informative product images in text and repeat essential image-only facts in the page content. Mark decorative images with an empty alternative.',
                'Check that each image has an alternative appropriate to its purpose and that essential facts remain readable without it.', priority='medium')
    for title, duplicates in titles.items():
        unique = {canonical(p):p for p in duplicates}
        if len(unique) > 1:
            quote = f'{len(unique)} distinct sampled pages publish the same title: {title}.'
            results.finding('seo.title_duplicate', duplicates[0].url, 'Different pages reuse the same search title', quote,
                'Give each distinct page a title that names its own product, service or subject. Update the shared template so new pages receive appropriate titles automatically.',
                'Compare titles across the affected pages and confirm that each identifies its own content.',
                root_cause='duplicate-title:' + title, items=[evidence(p.url, quote, 'html_title') for p in unique.values()])
    for description, duplicates in descriptions.items():
        if len({canonical(p) for p in duplicates}) > 1:
            results.suggest('seo.description_duplicate', duplicates[0].url,
                f'{len(duplicates)} sampled pages reuse the same meta description.',
                'Write descriptions around each page\'s actual offering or topic. Update the template to avoid applying the same generic description everywhere.',
                'Compare descriptions for the affected pages and confirm that each is accurate and distinctive.', priority='low')


def link_checks(pages, collector, results):
    """Reuse collected responses; at most eight new targets share a short allowance."""
    sources = defaultdict(list)
    targets = []
    for page in pages:
        preferred = canonical(page)
        if preferred != page.url:
            targets.append(('canonical', page, preferred))
        for link in page.links:
            try:
                target = normalize(link['url'])
            except (TypeError, ValueError):
                continue
            if not collector.scope.allows(target) or excluded_url(target):
                continue
            sources[target].append((page, link))
    # Explicit canonical targets, cached link failures, then useful uncached paths.
    targets += [('link', entries[0][0], target) for target, entries in sources.items()
                if target in collector.cache or any(e['in_main'] for _,e in entries)]
    seen = set()
    new_requests = 0
    for kind, page, target in targets:
        if (kind, target) in seen or not collector.scope.allows(target) or excluded_url(target):
            continue
        seen.add((kind, target))
        if target not in collector.cache:
            if new_requests >= 8:
                results.check('seo.links.budget', target, 'not_run', 'Additional link checks exceed the bounded sample.')
                continue
            new_requests += 1
        try:
            response = collector.fetch(target)
        except BudgetExceeded:
            results.check('seo.links.budget', target, 'not_run', 'Link-check allowance exhausted; cached evidence retained.')
            break
        if response.get('status') in (404, 410):
            referring = [page] if kind == 'canonical' else list({p.url:p for p,_ in sources[target]}.values())
            quote = f'{target} returned HTTP {response["status"]}.'
            results.finding('seo.canonical_broken' if kind == 'canonical' else 'seo.link_broken', referring[0].url,
                'Canonical points to a missing page' if kind == 'canonical' else 'Internal links lead to missing pages', quote,
                'Update the affected canonical declaration to the intended, accessible preferred page. Restore that page if its removal was accidental.' if kind == 'canonical' else
                'Replace links to the missing destination with the relevant working page. Restore the destination if visitors still need that content.',
                'Follow the corrected destination and confirm that it returns the intended content successfully.',
                entity=target, items=[evidence(p.url, quote, 'http') for p in referring])
        elif kind == 'canonical' and response.get('state') == 'ok' and 'html' in response.get('headers', {}).get('content-type',''):
            destination = Page(response)
            if noindex(destination):
                results.finding('seo.canonical_noindex', page.url, 'Canonical points to a page excluded from search',
                    f'The preferred URL {target} publishes a noindex directive.',
                    'Choose an indexable preferred page for content intended to appear in search. Align the canonical and index directives with that decision.',
                    'Confirm that the intended canonical destination is accessible and does not exclude the relevant search crawler.', entity=target)
            elif canonical(destination) not in (target, destination.url):
                results.suggest('seo.canonical_chain', page.url,
                    f'The canonical target {target} declares another preferred URL: {canonical(destination)}.',
                    'Point the page directly to the final intended canonical URL. Keep canonical declarations consistent across equivalent pages.',
                    'Inspect the source and destination and confirm that they agree on one preferred URL.', priority='medium')
