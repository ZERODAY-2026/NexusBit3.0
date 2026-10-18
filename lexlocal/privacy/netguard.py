"""Runtime network guard.

Patches socket connect/getaddrinfo/create_connection so the process can only talk to
loopback (127.0.0.0/8, ::1, localhost). Any other attempt raises PermissionError and is
recorded so the UI can show a blocked-attempt counter. This is defence in depth on top of
offline settings (HF_HUB_OFFLINE, Streamlit gatherUsageStats=false).
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import threading
import time

log = logging.getLogger("lexlocal.netguard")

_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}
_lock = threading.Lock()
_blocked: list[dict] = []
_active = False
_orig: dict = {}


def _is_loopback(host) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode(errors="ignore")
    host = str(host).strip("[]").split("%")[0]
    if host.lower() in _ALLOWED_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or (ip.version == 6 and ip.ipv4_mapped is not None and ip.ipv4_mapped.is_loopback)
    except ValueError:
        return False  # a hostname that is not localhost would need DNS -> block


def _record(host, port, via: str):
    entry = {"host": str(host), "port": port, "via": via, "time": time.strftime("%H:%M:%S")}
    with _lock:
        _blocked.append(entry)
    log.warning("netguard blocked outbound connection to %s:%s (%s)", host, port, via)


def _addr_host_port(address):
    if isinstance(address, tuple) and len(address) >= 2:
        return address[0], address[1]
    return None, None  # AF_UNIX etc. -> local


def _guarded_connect(self, address):
    host, port = _addr_host_port(address)
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(host):
        _record(host, port, "connect")
        raise PermissionError(f"LexLocal netguard: outbound connection to {host}:{port} blocked")
    return _orig["connect"](self, address)


def _guarded_connect_ex(self, address):
    host, port = _addr_host_port(address)
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(host):
        _record(host, port, "connect_ex")
        raise PermissionError(f"LexLocal netguard: outbound connection to {host}:{port} blocked")
    return _orig["connect_ex"](self, address)


def _guarded_getaddrinfo(host, port, *args, **kwargs):
    if not _is_loopback(host):
        _record(host, port, "dns")
        raise socket.gaierror(f"LexLocal netguard: DNS lookup for {host} blocked")
    return _orig["getaddrinfo"](host, port, *args, **kwargs)


def install() -> None:
    """Idempotently activate the guard for the whole process."""
    global _active
    with _lock:
        if _active:
            return
        _orig["connect"] = socket.socket.connect
        _orig["connect_ex"] = socket.socket.connect_ex
        _orig["getaddrinfo"] = socket.getaddrinfo
        socket.socket.connect = _guarded_connect
        socket.socket.connect_ex = _guarded_connect_ex
        socket.getaddrinfo = _guarded_getaddrinfo
        _active = True
    log.info("netguard active: loopback only")


def uninstall() -> None:
    global _active
    with _lock:
        if not _active:
            return
        socket.socket.connect = _orig["connect"]
        socket.socket.connect_ex = _orig["connect_ex"]
        socket.getaddrinfo = _orig["getaddrinfo"]
        _active = False


def is_active() -> bool:
    return _active


def blocked_attempts() -> list[dict]:
    with _lock:
        return list(_blocked)


def reset_counter() -> None:
    with _lock:
        _blocked.clear()
