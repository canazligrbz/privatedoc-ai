"""
AIR-GAP GÜVENLİK KATMANI
========================

Bu modül, uygulama sürecinin localhost dışındaki HİÇBİR adrese TCP bağlantısı
açamamasını garanti eder. Ağ yalıtımının yalnızca güvenlik duvarına bırakılmaması,
"defense in depth" ilkesi gereğidir: yanlışlıkla eklenen bir kütüphane
(ör. telemetri, model indirici) sessizce dışarı veri sızdıramaz.

Uygulanan üç katman:
  1. Ortam değişkenleri  -> HF/transformers/chromadb telemetri ve indirme kapatılır.
  2. socket monkey-patch -> localhost dışı connect() çağrıları AirGapViolation fırlatır.
  3. getaddrinfo kısıtı  -> Harici DNS çözümlemesi engellenir.

KULLANIM: Her giriş noktasının (app.py, ingest.py) EN ÜSTÜNDE, torch/transformers
importlarından ÖNCE çağrılmalıdır.

    from src.airgap import enforce_airgap
    enforce_airgap()
"""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Iterable, Set

__all__ = ["enforce_airgap", "AirGapViolation", "is_enforced", "selftest"]

_ENFORCED = False

_DEFAULT_ALLOWED: Set[str] = {
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "::",
    "localhost",
    "localhost.localdomain",
}

# Orijinal referanslar (yama öncesi) saklanır.
_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
_orig_create_connection = socket.create_connection
_orig_getaddrinfo = socket.getaddrinfo


class AirGapViolation(RuntimeError):
    """Uygulama dış ağa çıkmaya çalıştı. Bu bir güvenlik olayıdır."""


def _is_local(host: object) -> bool:
    if host is None:
        return True  # AF_UNIX vb.
    if isinstance(host, bytes):
        try:
            host = host.decode()
        except Exception:
            return False
    if not isinstance(host, str):
        return False
    h = host.strip().strip("[]").lower()
    if h in _DEFAULT_ALLOWED:
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _extract_host(address: object) -> object:
    if isinstance(address, tuple) and address:
        return address[0]
    return address


def _set_offline_env() -> None:
    """Kütüphaneleri zorla çevrimdışı moda alır."""
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", "models")
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")     # ChromaDB
    os.environ.setdefault("CHROMA_TELEMETRY_ENABLED", "False")
    os.environ.setdefault("POSTHOG_DISABLED", "1")
    os.environ.setdefault("DO_NOT_TRACK", "1")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("NO_PROXY", "*")
    # Kazara ayarlanmış proxy'leri temizle
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
        os.environ.pop(var, None)


def enforce_airgap(allowed_hosts: Iterable[str] | None = None,
                   block_network: bool = True) -> None:
    """Air-gap korumasını etkinleştirir. Birden çok kez çağrılabilir (idempotent)."""
    global _ENFORCED

    _set_offline_env()

    if not block_network or _ENFORCED:
        _ENFORCED = _ENFORCED or (not block_network)
        return

    if allowed_hosts:
        _DEFAULT_ALLOWED.update(h.lower() for h in allowed_hosts)

    def _guard(address: object, caller: str) -> None:
        host = _extract_host(address)
        if not _is_local(host):
            raise AirGapViolation(
                f"AIR-GAP İHLALİ ENGELLENDİ | {caller} -> {host!r}. "
                "Bu uygulama yalnızca localhost ile haberleşebilir. "
                "İlgili çağrıyı yapan bileşeni denetleyin."
            )

    def connect(self, address):                      # type: ignore[no-untyped-def]
        _guard(address, "socket.connect")
        return _orig_connect(self, address)

    def connect_ex(self, address):                   # type: ignore[no-untyped-def]
        _guard(address, "socket.connect_ex")
        return _orig_connect_ex(self, address)

    def create_connection(address, *args, **kwargs):  # type: ignore[no-untyped-def]
        _guard(address, "socket.create_connection")
        return _orig_create_connection(address, *args, **kwargs)

    def getaddrinfo(host, port, *args, **kwargs):     # type: ignore[no-untyped-def]
        if not _is_local(host):
            raise AirGapViolation(
                f"AIR-GAP İHLALİ ENGELLENDİ | DNS çözümlemesi -> {host!r}"
            )
        return _orig_getaddrinfo(host, port, *args, **kwargs)

    socket.socket.connect = connect            # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex      # type: ignore[method-assign]
    socket.create_connection = create_connection   # type: ignore[assignment]
    socket.getaddrinfo = getaddrinfo               # type: ignore[assignment]

    _ENFORCED = True


def is_enforced() -> bool:
    return _ENFORCED


def selftest() -> dict:
    """Korumanın gerçekten çalıştığını kanıtlar. verify_offline.py tarafından kullanılır."""
    results = {"localhost_allowed": None, "external_blocked": None}

    # 1) Harici adres bloklanmalı
    try:
        s = socket.socket()
        s.settimeout(2)
        s.connect(("8.8.8.8", 53))
        s.close()
        results["external_blocked"] = False
    except AirGapViolation:
        results["external_blocked"] = True
    except Exception:
        # Ağ zaten fiziksel olarak yoksa da "engellendi" sayılır ama koruma
        # aktifse AirGapViolation gelmeliydi -> ayırt etmek için işaretle.
        results["external_blocked"] = "network_unreachable"

    # 2) Localhost'a bağlantı denemesi patch tarafından engellenmemeli
    try:
        s = socket.socket()
        s.settimeout(1)
        s.connect_ex(("127.0.0.1", 11434))
        s.close()
        results["localhost_allowed"] = True
    except AirGapViolation:
        results["localhost_allowed"] = False
    except Exception:
        results["localhost_allowed"] = True  # bağlantı reddi normaldir, engel değil

    return results
