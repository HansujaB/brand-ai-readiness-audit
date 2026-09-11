"""Connection-time IP pinning; keep original TLS hostname and HTTP Host.
Sources: OWASP SSRF Prevention; urllib3 Advanced Usage / custom SNI.
"""
import ipaddress
import socket
from urllib.parse import urlsplit
import certifi
import urllib3
from requests.adapters import HTTPAdapter


class PinnedAdapter(HTTPAdapter):
    def __init__(self):
        super().__init__(max_retries=0)
        self.pinned_pools = {}

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        if request.method != 'GET' or verify is False or cert or proxies:
            raise ValueError('Only anonymous verified direct GET requests are supported')
        target = urlsplit(request.url)
        addresses = socket.getaddrinfo(target.hostname, target.port or (443 if target.scheme == 'https' else 80), type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('Connection-time non-public address refused')
        # The pool connects to this numeric address, never resolves the hostname again.
        address = addresses[0][4][0]
        key = (target.scheme, target.hostname, target.port, address)
        if key not in self.pinned_pools:
            if target.scheme == 'https':
                pool = urllib3.HTTPSConnectionPool(address, target.port or 443, server_hostname=target.hostname,
                    assert_hostname=target.hostname, cert_reqs='CERT_REQUIRED', ca_certs=certifi.where(), maxsize=1)
            else:
                pool = urllib3.HTTPConnectionPool(address, target.port or 80, maxsize=1)
            self.pinned_pools[key] = pool
        headers = dict(request.headers)
        headers['Host'] = target.netloc
        headers.pop('Cookie', None)
        headers.pop('Authorization', None)
        response = self.pinned_pools[key].urlopen('GET', request.path_url, headers=headers, redirect=False,
            retries=False, preload_content=False, decode_content=False, assert_same_host=False,
            timeout=urllib3.Timeout(connect=timeout, read=timeout))
        return self.build_response(request, response)

    def close(self):
        for pool in self.pinned_pools.values():
            pool.close()
        super().close()
