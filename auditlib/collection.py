"""Shared bounded, anonymous, robots-enforcing evidence collection."""
import hashlib
import ipaddress
import re
import socket
import posixpath
from contextlib import contextmanager
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, urljoin, quote, unquote, parse_qsl

import requests

AGENT = 'BrandReadinessAudit'
CRAWLERS = {
    'OAI-SearchBot': 'search', 'GPTBot': 'training', 'ChatGPT-User': 'user_triggered',
    'Googlebot': 'search', 'Bingbot': 'search', 'PerplexityBot': 'search',
    'ClaudeBot': 'training', 'CCBot': 'training',
    'Google-Extended': 'training_control', 'Applebot-Extended': 'training_control',
}
PRIVATE = re.compile(r'/(?:cart|checkout|account|admin|login|logout|signout|delete|unsubscribe)(?:/|$)', re.I)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def normalize(url):
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('An absolute HTTP(S) URL without credentials is required')
    if p.port not in (None, 80, 443):
        raise ValueError('Only public HTTP(S) ports are supported')
    host = p.hostname.encode('idna').decode('ascii').lower()
    if ':' in host:
        host = '[' + host + ']'
    port = p.port if p.port != (443 if p.scheme == 'https' else 80) else None
    path = re.sub(r'%([0-9a-fA-F]{2})', lambda m: chr(int(m[1],16)) if chr(int(m[1],16)) in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~' else '%' + m[1].upper(), p.path or '/')
    path = posixpath.normpath(path) + ('/' if path.endswith('/') and path != '/' else '')
    return urlunsplit((p.scheme.lower(), host + (':' + str(port) if port else ''), path, p.query, ''))


def origin(url):
    p = urlsplit(url)
    return p.scheme + '://' + p.netloc


def excluded_url(url):
    """Conservative local action policy; not a robots or authentication claim."""
    p = urlsplit(url)
    path = p.path
    for _ in range(8):
        decoded = unquote(path)
        if decoded == path:
            break
        path = decoded
    else:
        return True
    path = posixpath.normpath(path.replace('\\', '/'))
    if PRIVATE.search(path):
        return True
    query = [(unquote(k).lower(), unquote(v).lower()) for k,v in parse_qsl(p.query)]
    return any(k in ('action','do') and v in ('delete','logout','buy','remove','unsubscribe') for k,v in query)


def public_url(url):
    url = normalize(url)
    host = urlsplit(url).hostname
    addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Non-public network destination refused')
    return url


def path_octets(value):
    value = quote(value, safe='/%?=&:$*+;,@!()~')
    def decode(m):
        c = chr(int(m[1], 16))
        return c if re.match(r'[A-Za-z0-9._~-]', c) else '%' + m[1].upper()
    return re.sub(r'%([0-9a-fA-F]{2})', decode, value)


class Robots:
    """Merged matching groups, longest rule, Allow wins equal specificity."""
    def __init__(self, text='', status=200):
        self.status = status
        self.groups = []
        self.sitemaps = []
        agents, rules, delay, has_directive = [], [], 0, False
        for line in text.splitlines() + ['User-agent: __end__']:
            key, sep, value = line.split('#', 1)[0].partition(':')
            if not sep:
                continue
            key, value = key.strip().lower(), value.strip()
            if key == 'user-agent':
                if has_directive:
                    self.groups.append((agents, rules, delay))
                    agents, rules, delay, has_directive = [], [], 0, False
                agents.append(value.lower())
            elif key in ('allow', 'disallow') and agents:
                has_directive = True
                if value:
                    rules.append((key, value))
            elif key == 'crawl-delay' and agents:
                has_directive = True
                try:
                    delay = max(0, float(value))
                except ValueError:
                    pass
            elif key == 'sitemap':
                self.sitemaps.append(value)

    def decision(self, agent, url):
        if self.status == 429 or self.status >= 500 or self.status == 0:
            return None, 'robots.txt unavailable; permission unknown', 0
        if 400 <= self.status < 500:
            return True, 'robots.txt absent (HTTP %s)' % self.status, 0
        matches = [g for g in self.groups if any(a != '*' and a in agent.lower() for a in g[0])]
        if matches:
            specificity = max(len(a) for g in matches for a in g[0] if a != '*' and a in agent.lower())
            matches = [g for g in matches if any(len(a) == specificity and a in agent.lower() for a in g[0])]
        if not matches:
            matches = [g for g in self.groups if '*' in g[0]]
        p = urlsplit(url)
        path = path_octets(p.path + ('?' + p.query if p.query else ''))
        applicable = []
        for _, rules, _ in matches:
            for directive, rule in rules:
                rule = path_octets(rule)
                pattern = re.escape(rule).replace(r'\*', '.*')
                pattern = pattern[:-2] + '$' if rule.endswith('$') else pattern
                if re.match('^' + pattern, path):
                    applicable.append((len(rule.replace('*', '').rstrip('$')), directive == 'allow', directive + ': ' + rule))
        winner = max(applicable, default=(0, True, 'no matching exclusion'))
        return winner[1], winner[2], max((g[2] for g in matches), default=0)


class BudgetExceeded(Exception):
    pass


class DownloadLimit(Exception):
    def __init__(self, scope, limit):
        self.scope, self.limit = scope, limit
        super().__init__(f'{scope} decoded-body limit reached ({limit:,} bytes); response incomplete')


class Collector:
    def __init__(self, seconds=270, max_requests=80, transport=None, validator=public_url,
                 max_response_bytes=20_000_000, max_download_bytes=100_000_000):
        self.started = time.monotonic()
        self.deadline = self.started + seconds
        self.max_requests = max_requests
        if max_response_bytes <= 0 or max_download_bytes <= 0:
            raise ValueError('Download limits must be positive')
        self.max_response_bytes = max_response_bytes
        self.max_download_bytes = max_download_bytes
        self.downloaded_bytes = 0
        self.session = requests.Session()
        self.session.trust_env = False
        from .network import PinnedAdapter
        self.session.mount('https://', PinnedAdapter())
        self.session.mount('http://', PinnedAdapter())
        self.phase_deadline = self.deadline
        self.phase_request_limit = max_requests
        self.transport = transport
        self.validator = validator
        self.cache, self.robots, self.log, self.last_request = {}, {}, [], {}

    def remaining(self):
        left = min(self.deadline, self.phase_deadline) - time.monotonic()
        if left <= 0:
            raise BudgetExceeded('Global work deadline reached')
        return left

    @contextmanager
    def allowance(self, seconds, requests):
        previous = self.phase_deadline, self.phase_request_limit
        self.phase_deadline = min(self.deadline, time.monotonic() + max(0, seconds))
        self.phase_request_limit = min(self.max_requests, len(self.log) + max(0, requests))
        try:
            yield
        finally:
            self.phase_deadline, self.phase_request_limit = previous

    def read_body(self, chunks, entry):
        """Count decoded bytes across all network responses, including failed bodies.

        Streaming can observe one extra chunk (up to 16 KiB) before detecting
        a limit. Truncated evidence is never parsed or fulfilled to a browser.
        """
        body = bytearray()
        for chunk in chunks:
            self.remaining()
            entry['bytes_received'] += len(chunk)
            self.downloaded_bytes += len(chunk)
            if self.downloaded_bytes > self.max_download_bytes:
                raise DownloadLimit('total_download', self.max_download_bytes)
            if entry['bytes_received'] > self.max_response_bytes:
                raise DownloadLimit('per_response', self.max_response_bytes)
            body.extend(chunk)
        return bytes(body)

    def wire(self, url):
        self.remaining()
        url = self.validator(url)
        if self.downloaded_bytes >= self.max_download_bytes:
            raise BudgetExceeded('Global download budget exhausted; no further requests sent')
        if len(self.log) >= min(self.max_requests, self.phase_request_limit):
            raise BudgetExceeded('Global request limit reached')
        started = time.monotonic()
        entry = {'url': url, 'method': 'GET', 'observed_at': utcnow(), 'bytes_received': 0}
        self.log.append(entry)
        result = {}
        try:
            if self.transport:
                result = dict(self.transport(url))
                body = result.pop('body', b'')
                entry['status'] = result['status']
                result['body'] = self.read_body((body[i:i+16384] for i in range(0, len(body), 16384)), entry)
            else:
                self.session.cookies.clear()
                with self.session.get(url, headers={'User-Agent': AGENT + '/2.0 (anonymous read-only audit)'},
                                      timeout=min(10, self.remaining()), allow_redirects=False, stream=True) as response:
                    result = {'status': response.status_code, 'headers': dict(response.headers),
                              'headers_seconds': response.elapsed.total_seconds()}
                    entry['status'] = response.status_code
                    if hasattr(response.raw, 'headers') and hasattr(response.raw.headers, 'getlist'):
                        tags = response.raw.headers.getlist('X-Robots-Tag')
                        if tags:
                            result['headers']['X-Robots-Tag'] = tags
                    result['body'] = self.read_body(response.iter_content(16384), entry)
        except DownloadLimit as exc:
            entry.update(error=str(exc), limit_scope=exc.scope)
            result.update(state='incomplete', body=b'', reason=str(exc), limit_scope=exc.scope,
                          configured_limit_bytes=exc.limit, truncated=True)
        except Exception as exc:
            entry['error'] = str(exc)
            raise
        result['headers'] = {k.lower(): v for k, v in result.get('headers', {}).items()}
        result.update(url=url, observed_at=entry['observed_at'], total_seconds=time.monotonic() - started,
                      bytes_received=entry['bytes_received'])
        return result

    def policy(self, url):
        base = origin(url)
        if base not in self.robots:
            current = base + '/robots.txt'
            try:
                for _ in range(6):
                    response = self.wire(current)
                    if response.get('state') == 'incomplete':
                        self.robots[base] = Robots(status=0)
                        break
                    if response['status'] in (301, 302, 303, 307, 308):
                        current = normalize(urljoin(current, response['headers'].get('location', '')))
                        # Only the robots bootstrap follows redirects without a prior policy.
                        continue
                    self.robots[base] = Robots(response['body'].decode('utf-8', 'replace'), response['status'])
                    break
                else:
                    self.robots[base] = Robots(status=0)
            except BudgetExceeded:
                raise
            except Exception:
                self.robots[base] = Robots(status=0)
        return self.robots[base]

    def fetch(self, url):
        url = normalize(url)
        if url in self.cache:
            return self.cache[url]
        initial, visited = url, set()
        try:
            for _ in range(6):
                self.remaining()
                url = self.validator(url)
                if url in visited:
                    raise ValueError('Redirect loop')
                visited.add(url)
                if excluded_url(url):
                    raise ValueError('Transactional path excluded')
                allowed, reason, delay = self.policy(url).decision(AGENT, url)
                if allowed is not True:
                    return self.store(initial, {'url': url, 'state': 'blocked' if allowed is False else 'unknown', 'reason': reason})
                if url in self.cache:
                    return self.store(initial, self.cache[url])
                wait = max(0, max(delay, .15) - (time.monotonic() - self.last_request.get(origin(url), 0)))
                if wait >= self.remaining():
                    raise BudgetExceeded('Crawl delay exceeds remaining budget')
                time.sleep(wait)
                response = self.wire(url)
                self.last_request[origin(url)] = time.monotonic()
                if response.get('state') == 'incomplete':
                    return self.store(initial, response)
                if response['status'] in (301, 302, 303, 307, 308):
                    if not response['headers'].get('location'):
                        raise ValueError('Redirect has no Location')
                    url = normalize(urljoin(url, response['headers']['location']))
                    continue
                response['state'] = 'ok' if response['status'] < 400 else 'http_error'
                response['sha256'] = hashlib.sha256(response['body']).hexdigest()
                self.cache[url] = response
                return self.store(initial, response)
            raise ValueError('Redirect limit reached')
        except BudgetExceeded:
            raise
        except Exception as exc:
            return self.store(initial, {'url': url, 'state': 'unknown', 'reason': str(exc)})

    def store(self, url, response):
        self.cache[url] = response
        return response
