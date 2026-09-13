"""Identity evidence from the audited website only."""
from .diagnostics import evidence, norm


def published_brand(page):
    """Prefer the site's published display name over a guessed company name."""
    for selector in ('meta[property="og:site_name"]', 'meta[name="application-name"]'):
        meta = page.soup.select_one(selector)
        if meta and meta.get('content', '').strip():
            return meta['content'].strip()
    for kind in ('WebSite', 'Organization', 'Corporation', 'LocalBusiness'):
        for node in page.nodes:
            kinds = node.get('@type', [])
            kinds = kinds if isinstance(kinds, list) else [kinds]
            name = node.get('name')
            if kind in kinds and isinstance(name, str) and name.strip():
                return name.strip()
    return None


def identity_checks(pages, brand, results):
    observations = []
    for page in pages:
        for node in page.nodes:
            kinds = node.get('@type', [])
            kinds = kinds if isinstance(kinds, list) else [kinds]
            if set(kinds) & {'Organization', 'Corporation', 'LocalBusiness'} and node.get('name'):
                observations.append((page, node))
    if not pages:
        return
    identifying = [(p,n) for p,n in observations if n.get('url') or n.get('address') or n.get('sameAs')]
    results.check('identity.context', pages[0].url, 'pass' if identifying else 'unknown',
        'Website organization identity evidence collected.' if identifying else 'No structured organization identity resolved; inspect visible about/contact content.',
        [evidence(p.url, str(n), 'structured_data') for p,n in identifying[:3]])
    by_id = {}
    for page, node in observations:
        key = node.get('@id')
        if key:
            by_id.setdefault(key, []).append((page,node))
    for key, entries in by_id.items():
        if len({norm(n['name']) for _,n in entries}) > 1:
            results.review('identity.names', entries[0][0].url, 'Which organization name should this shared identifier use?',
                'The same structured identifier has different names; trading names and legal names may explain the difference.',
                [evidence(p.url, str(n), 'structured_data') for p,n in entries])
