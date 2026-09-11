"""Entity disambiguation using collected organization evidence."""
from urllib.parse import urlsplit
from .diagnostics import evidence, norm


def organizations(page):
    for node in page.nodes:
        kinds = node.get('@type', [])
        kinds = kinds if isinstance(kinds, list) else [kinds]
        if any(kind in ('Organization', 'Corporation', 'LocalBusiness', 'Person') for kind in kinds):
            yield node


def identity_checks(pages, external_pages, brand, results):
    own = [(p, node) for p in pages for node in organizations(p) if norm(node.get('name', '')) == norm(brand)]
    competitors = []
    for p in external_pages:
        for node in organizations(p):
            official = node.get('url')
            if not isinstance(official, str) or not official.startswith(('http://', 'https://')):
                continue
            if norm(node.get('name', '')) == norm(brand) and all(urlsplit(official).hostname != urlsplit(site.url).hostname for site in pages):
                competitors.append((p, node))
    if not pages:
        return
    identified = any(n.get('address') or n.get('sameAs') or n.get('url') for _, n in own)
    if competitors and not identified:
        p, node = competitors[0]
        items = [evidence(p.url, str(node), 'structured_data'), evidence(pages[0].url, pages[0].main_text[:700])]
        results.suggest('identity.disambiguation', pages[0].url, str(node),
                        'A sampled organization uses this name with another official domain. Clarify your organization, location, official domain and verified identity links.',
                        'Verify both organizations and confirm that the brand page resolves to the intended entity.')
        results.check('identity.resolution', pages[0].url, 'unknown', 'Same-name organization with a different official URL observed; relationship/ownership needs review.', items)
    else:
        results.check('identity.resolution', pages[0].url, 'pass' if own and identified else 'unknown',
                      'Organization identifying context observed.' if own and identified else 'No verified identity collision; absent sameAs alone is not a defect.')
