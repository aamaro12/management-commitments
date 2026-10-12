"""Public HTTPS only, pinned to checked DNS answers and bounded at each redirect."""

import http.client
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit
import io
import zipfile

from . import __version__
from .sources import EvidenceError, MAX_BYTES, public_url


def addresses(host):
    ips = list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
    if not ips or any(not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast for ip in ips):
        raise EvidenceError("Acquisition is limited to public Internet addresses")
    return ips


class Connection(http.client.HTTPSConnection):
    def __init__(self, host, ip):
        super().__init__(host, timeout=25)
        self.ip = ip

    def connect(self):
        sock = socket.create_connection((self.ip, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def fetch(url, allowed_hosts):
    current = public_url(url)
    redirects = []
    for _ in range(6):
        p = urlsplit(public_url(current))
        if p.hostname.lower() not in allowed_hosts:
            raise EvidenceError("Host is outside the explicitly allowed source hosts")
        conn = Connection(p.hostname, addresses(p.hostname)[0])
        try:
            conn.request(
                "GET",
                (p.path or "/") + ("?" + p.query if p.query else ""),
                headers={
                    "User-Agent": f"management-commitments/{__version__} public research; contact github.com/aamaro12",
                    "Accept": "text/html,application/pdf,text/plain",
                    "Accept-Encoding": "identity",
                },
            )
            r = conn.getresponse()
            if r.status in (301, 302, 303, 307, 308):
                target = r.getheader("Location")
                if not target:
                    raise EvidenceError("Redirect has no location")
                target = public_url(urljoin(current, target))
                redirects.append({"from": current, "to": target, "status": r.status})
                current = target
                continue
            if r.status != 200:
                raise EvidenceError(f"HTTP {r.status}")
            if int(r.getheader("Content-Length") or 0) > MAX_BYTES:
                raise EvidenceError("Response exceeds 12 MiB")
            raw = r.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise EvidenceError("Response exceeds 12 MiB")
            header = r.getheader("Content-Type") or ""
            content_type = header.split(";")[0].strip().lower()
            charset = next(
                (
                    p.split("=", 1)[1].strip().strip("\"'")
                    for p in header.split(";")[1:]
                    if p.strip().lower().startswith("charset=")
                ),
                None,
            )
            format = (
                "pdf"
                if raw.startswith(b"%PDF")
                else {"text/html": "html", "text/plain": "txt", "application/pdf": "pdf"}.get(content_type)
            )
            if raw.startswith(b"PK"):
                try:
                    with zipfile.ZipFile(io.BytesIO(raw)) as z:
                        names = z.namelist()
                except zipfile.BadZipFile:
                    names = []
                format = "docx" if "word/document.xml" in names else "pptx" if "ppt/presentation.xml" in names else None
            if not format:
                raise EvidenceError(f"Unsupported response type: {content_type}")
            return {
                "raw": raw,
                "url": current,
                "format": format,
                "charset": charset,
                "redirects": redirects,
                "http_status": 200,
            }
        finally:
            conn.close()
    raise EvidenceError("Redirect budget exhausted")
