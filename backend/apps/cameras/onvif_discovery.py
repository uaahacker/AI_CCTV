"""IP-camera discovery on the local network — stdlib only.

Two methods, both safe to call from a request handler:

- ``ws_discovery(timeout)`` — UDP multicast WS-Discovery (ONVIF). Most
  recent IP cameras respond with a SOAP envelope containing their XAddrs
  (HTTP service endpoint) and "Scopes" (manufacturer, model, hardware).
- ``probe_subnet(cidr, timeout)`` — fast TCP-connect scan to port 554 (RTSP)
  for environments where multicast is blocked (cloud VMs, hotel WiFi, etc.).

Neither method touches the camera credentials. The returned dicts include
a ``rtsp_hint`` you can use as a starting point when the user creates the
``Camera`` record.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import socket
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

logger = logging.getLogger(__name__)

WSD_MULTICAST_ADDR = "239.255.255.250"
WSD_PORT = 3702

_WSD_PROBE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
            xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
            xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <e:Header>
    <w:MessageID>uuid:{msg_id}</w:MessageID>
    <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
    <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
  </e:Header>
  <e:Body>
    <d:Probe>
      <d:Types>dn:NetworkVideoTransmitter</d:Types>
    </d:Probe>
  </e:Body>
</e:Envelope>"""

_XADDRS_RE = re.compile(r"<[^>]*XAddrs[^>]*>([^<]+)</[^>]*XAddrs[^>]*>", re.IGNORECASE)
_SCOPES_RE = re.compile(r"<[^>]*Scopes[^>]*>([^<]+)</[^>]*Scopes[^>]*>", re.IGNORECASE)
_HW_RE = re.compile(r"onvif://www\.onvif\.org/(name|hardware|location)/([^\s]+)", re.IGNORECASE)
_HOST_RE = re.compile(r"https?://([^/:]+)(?::\d+)?", re.IGNORECASE)


def ws_discovery(timeout: float = 3.0) -> list[dict]:
    """Send a ONVIF WS-Discovery probe and collect responses."""
    msg_id = uuid.uuid4()
    probe = _WSD_PROBE_TEMPLATE.format(msg_id=msg_id).encode("utf-8")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(timeout)
    try:
        try:
            sock.bind(("", 0))
        except OSError as exc:
            logger.warning("WS-Discovery bind failed: %s", exc)
            return []
        try:
            sock.sendto(probe, (WSD_MULTICAST_ADDR, WSD_PORT))
        except OSError as exc:
            logger.warning("WS-Discovery sendto failed (multicast blocked?): %s", exc)
            return []

        seen: dict[str, dict] = {}
        while True:
            try:
                data, addr = sock.recvfrom(8192)
            except socket.timeout:
                break
            except OSError:
                break
            cand = _parse_wsd_response(data.decode("utf-8", errors="replace"), addr[0])
            if cand and cand["ip"] not in seen:
                seen[cand["ip"]] = cand
        return list(seen.values())
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _parse_wsd_response(body: str, sender_ip: str) -> dict | None:
    xaddrs = ""
    m = _XADDRS_RE.search(body)
    if m:
        xaddrs = m.group(1).strip().split()[0] if m.group(1).strip() else ""

    ip = sender_ip
    host_match = _HOST_RE.match(xaddrs)
    if host_match:
        ip = host_match.group(1)

    scopes = ""
    s = _SCOPES_RE.search(body)
    if s:
        scopes = s.group(1)
    info: dict[str, str] = {}
    for key, val in _HW_RE.findall(scopes or ""):
        info[key.lower()] = val.replace("_", " ")

    return {
        "ip": ip,
        "rtsp_hint": f"rtsp://{ip}:554/",
        "onvif_xaddrs": xaddrs,
        "manufacturer": info.get("name", ""),
        "model": info.get("hardware", ""),
        "location": info.get("location", ""),
        "method": "ws-discovery",
    }


def probe_subnet(cidr: str, *, timeout: float = 1.0, max_workers: int = 64) -> list[dict]:
    """TCP-connect probe to port 554 across every host in ``cidr``.

    Returns one entry per host that completes the TCP handshake. Hard-capped
    at /22 (1024 hosts) so we never run a multi-thousand-host scan from a
    web request.
    """
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        raise ValueError(f"Invalid CIDR: {exc}")
    if net.num_addresses > 1024:
        raise ValueError("Refusing to scan a subnet larger than /22 from the API.")

    hosts: Iterable[str] = (str(h) for h in net.hosts())

    def _probe(ip: str) -> dict | None:
        try:
            with socket.create_connection((ip, 554), timeout=timeout):
                return {
                    "ip": ip,
                    "rtsp_hint": f"rtsp://{ip}:554/",
                    "method": "tcp-554",
                }
        except OSError:
            return None

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for cand in pool.map(_probe, hosts):
            if cand is not None:
                results.append(cand)
    return results
