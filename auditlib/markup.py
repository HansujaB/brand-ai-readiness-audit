"""Conservative nested microdata/RDFa subset. Unsupported references stay explicit."""

def scoped_nodes(soup):
    for selector, type_key, prop, kind in [('[itemscope]', 'itemtype', 'itemprop', 'microdata'), ('[typeof]', 'typeof', 'property', 'rdfa')]:
        scopes = soup.select(selector)
        if not scopes:
            continue
        limits = []
        def parse(scope):
            types = [t.rsplit('/', 1)[-1].rsplit(':', 1)[-1] for t in scope.get(type_key, '').split()]
            node = {'@type': types[0] if len(types) == 1 else types}
            identity = scope.get('itemid' if kind == 'microdata' else 'about')
            if identity:
                node['@id'] = identity
            if scope.get('itemref') or scope.get('resource') or scope.get('prefix') or scope.get('rev'):
                limits.append('References, custom prefixes and reverse RDFa relationships are not fully resolved.')
            for element in scope.select('[' + prop + ']' + (',[rel]' if kind == 'rdfa' else '')):
                parent = element.find_parent(attrs={type_key: True}) if kind == 'rdfa' else element.find_parent(attrs={'itemscope': True})
                if parent is not scope:
                    continue
                nested = element.has_attr(type_key if kind == 'rdfa' else 'itemscope')
                related = element.find(attrs={'typeof':True}) if kind == 'rdfa' and element.has_attr('rel') else None
                value = parse(element) if nested else parse(related) if related else next((element.get(k) for k in ('content','datetime','resource','href','src','value') if element.has_attr(k)), element.get_text(' ', strip=True))
                properties = element.get(prop, element.get('rel', ''))
                properties = properties if isinstance(properties, list) else properties.split()
                for key in properties:
                    key = key.rsplit('/', 1)[-1].rsplit(':', 1)[-1]
                    if key in node:
                        node[key] = (node[key] if isinstance(node[key], list) else [node[key]]) + [value]
                    else:
                        node[key] = value
            return node
        # Each scope is available for inspection; parent relationships remain nested.
        yield kind, [parse(scope) for scope in scopes], list(dict.fromkeys(limits))
