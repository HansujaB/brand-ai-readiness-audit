"""Resolve a single website locale without guessing the visitor's location."""
import re
from urllib.parse import urlsplit, urljoin, parse_qs
from .collection import normalize, origin

COUNTRIES = set('ad ae af ag ai al am ao aq ar as at au aw ax az ba bb bd be bf bg bh bi bj bl bm bn bo bq br bs bt bv bw by bz ca cc cd cf cg ch ci ck cl cm cn co cr cu cv cw cx cy cz de dj dk dm do dz ec ee eg eh er es et fi fj fk fm fo fr ga gb gd ge gf gg gh gi gl gm gn gp gq gr gs gt gu gw gy hk hm hn hr ht hu id ie il im in io iq ir is it je jm jo jp ke kg kh ki km kn kp kr kw ky kz la lb lc li lk lr ls lt lu lv ly ma mc md me mf mg mh mk ml mm mn mo mp mq mr ms mt mu mv mw mx my mz na nc ne nf ng ni nl no np nr nu nz om pa pe pf pg ph pk pl pm pn pr ps pt pw py qa re ro rs ru rw sa sb sc sd se sg sh si sj sk sl sm sn so sr ss st sv sx sy sz tc td tf tg th tj tk tl tm tn to tr tt tv tw tz ua ug um us uy uz va vc ve vg vi vn vu wf ws ye yt za zm zw'.split())
LANGUAGES = set('aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu'.split())


def language_tag(value):
    return (value or '').replace('_', '-').lower().strip()


def tag_parts(tag):
    parts = language_tag(tag).split('-')
    lang = parts[0] if parts[0] in LANGUAGES else None
    country = next((x for x in parts[1:] if x in COUNTRIES), None)
    return country, lang


def url_locale(url, sitemap=False):
    p = urlsplit(url)
    parts = [x.lower() for x in p.path.strip('/').split('/') if x]
    country = lang = None
    prefix = ''
    if len(parts) >= 2 and parts[0] in COUNTRIES and parts[1] in LANGUAGES:
        country, lang, prefix = parts[0], parts[1], '/' + '/'.join(parts[:2]) + '/'
    elif parts:
        country, lang = tag_parts(parts[0])
        if lang:
            prefix = '/' + parts[0] + '/'
        elif parts[0] in COUNTRIES:
            country, prefix = parts[0], '/' + parts[0] + '/'
    query = parse_qs(p.query)
    for key in ('locale', 'lang', 'language'):
        if query.get(key):
            c, l = tag_parts(query[key][0]); country, lang = c or country, l or lang
    for key in ('country', 'market'):
        if query.get(key) and query[key][0].lower() in COUNTRIES:
            country = query[key][0].lower()
    if sitemap and not (country or lang):
        tokens = re.split(r'[^a-z]+', p.path.lower())
        for i, token in enumerate(tokens[:-1]):
            if token in LANGUAGES and tokens[i+1] in COUNTRIES:
                lang, country = token, tokens[i+1]
                break
            if token in COUNTRIES and tokens[i+1] in LANGUAGES:
                country, lang = token, tokens[i+1]
                break
    return country, lang, prefix


class SiteScope:
    def __init__(self, site, country=None, language=None):
        self.site = normalize(site)
        self.origin = origin(self.site)
        c, l, self.prefix = url_locale(site)
        self.country = country.lower() if country else tag_parts(language)[0] or c
        self.language = language_tag(language) if language else l
        self.explicit_country, self.explicit_language = country, language
        self.resolved = False
        self.reason = 'Explicit options or starting URL; awaiting document metadata.'

    def same_origin(self, url):
        try:
            return origin(normalize(url)) == self.origin
        except (ValueError, AttributeError):
            return False

    def allows(self, url, purpose='page'):
        if not self.same_origin(url):
            return False
        if purpose == 'asset':
            return True  # Shared assets can live outside locale paths on this origin.
        if not self.resolved:
            return True  # Only the entry document and its redirects bootstrap locale selection.
        c, l, _ = url_locale(url, purpose == 'sitemap')
        selected_language = (self.language or '').split('-')[0]
        return not ((c and c != self.country) or (l and l != selected_language))

    def resolve(self, page):
        """Return a published alternate to collect, if the entry is a locale selector."""
        c, l, prefix = url_locale(page.url)
        html_c, html_l = tag_parts(page.lang)
        meta = page.soup.select_one('meta[property="og:locale"]')
        meta_c, meta_l = tag_parts(meta.get('content', '')) if meta else (None, None)
        self.country = self.country or c or html_c or meta_c
        self.language = self.language or l or html_l or meta_l
        alternatives = []
        for link in page.soup.select('link[hreflang][href],a[hreflang][href]'):
            url = urljoin(page.url, link['href'])
            if not self.same_origin(url):
                continue
            ac, al = tag_parts(link['hreflang'])
            uc, ul, _ = url_locale(url)
            alternatives.append((ac or uc, al or ul, normalize(url), link['hreflang'] == 'x-default'))
        for link in page.links:
            if self.same_origin(link['url']):
                ac, al, _ = url_locale(link['url'])
                if al:
                    alternatives.append((ac, al, normalize(link['url']), False))
        matches = [a for a in alternatives if (a[0] or a[1]) and (not self.country or a[0] == self.country) and
                   (not self.language or a[1] == self.language.split('-')[0])]
        matches.sort(key=lambda a: (not a[3], a[2]))
        target = None
        if matches:
            chosen = matches[0]
            if (not self.country and chosen[0]) or (not self.language and chosen[1]) or \
               (self.explicit_country and (c or html_c) != self.country) or \
               (self.explicit_language and (l or html_l) != self.language.split('-')[0]):
                self.country = self.country or chosen[0]
                self.language = self.language or chosen[1]
                target = chosen[2] if chosen[2] != page.url else None
        tld = urlsplit(page.url).hostname.rsplit('.', 1)[-1]
        self.country = self.country or (tld if tld in COUNTRIES else None)
        self.prefix = url_locale(target or page.url)[2] or prefix
        self.resolved = True
        self.reason = 'Resolved from options, URL, document locale, published alternates and country domain, in that order. No location guessed.'
        return target

    def accepts_document(self, page):
        c, l = tag_parts(page.lang)
        return self.allows(page.url) and not ((c and self.country and c != self.country) or
            (l and self.language and l != self.language.split('-')[0]))

    def rank(self, url):
        return (not bool(self.prefix and urlsplit(url).path.startswith(self.prefix)), len(url), url)

    def as_dict(self):
        return {'origin': self.origin, 'country': self.country.upper() if self.country else None,
                'language': self.language, 'path_prefix': self.prefix or '/',
                'selection': self.reason, 'website_only': True,
                'audience': 'country' if self.country else 'site default/global; no country published'}
