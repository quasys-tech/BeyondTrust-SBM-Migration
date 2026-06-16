# -*- coding: utf-8 -*-
"""
OS envanteri arama indeksi.

OsEnvanter satırlarını iki ayrı sözlüğe (dictionary) indeksler:
  * IP adresine göre
  * Hostname'e göre (büyük/küçük harf duyarsız)

remoteMachines içindeki bir değer geldiğinde, değerin IP mi hostname mi
olduğuna bakar ve uygun indekste arar.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from common.logging_setup import get_logger
from correlation.models import OsRecord

log = get_logger("os_inventory")

# Basit IPv4 deseni (192.168.1.1 gibi). Port/maske içermez.
_IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def looks_like_ip(value: str) -> bool:
    """Verilen metin IPv4 adresi gibi mi görünüyor?"""
    return bool(_IPV4_RE.match(value.strip()))


class OsInventory:
    """OsEnvanter kayıtları üzerinde hızlı arama sağlar."""

    def __init__(self, records: List[OsRecord]):
        self._by_ip: Dict[str, OsRecord] = {}
        self._by_hostname: Dict[str, OsRecord] = {}
        # OsEnvanter'da birden fazla kez geçen (belirsiz) anahtarlar:
        self._dup_ips: set = set()
        self._dup_hostnames: set = set()
        self._build_index(records)

    def _build_index(self, records: List[OsRecord]) -> None:
        for rec in records:
            if rec.ip_address:
                key = rec.ip_address.strip()
                if key in self._by_ip:
                    self._dup_ips.add(key)  # belirsiz -> korelasyonda ignore edilecek
                    log.warning(
                        "Tekrarlanan IP '%s' (satır %d) -> BELİRSİZ; bu IP'li token'lar ignore edilecek.",
                        key, rec.source_row,
                    )
                else:
                    self._by_ip[key] = rec

            if rec.hostname:
                key = rec.hostname.strip().lower()
                if key in self._by_hostname:
                    self._dup_hostnames.add(key)
                    log.warning(
                        "Tekrarlanan hostname '%s' (satır %d) -> BELİRSİZ; bu hostname'li token'lar ignore edilecek.",
                        rec.hostname, rec.source_row,
                    )
                else:
                    self._by_hostname[key] = rec

        log.info(
            "OS indeksi hazır: %d IP, %d hostname (belirsiz: %d IP, %d hostname).",
            len(self._by_ip), len(self._by_hostname),
            len(self._dup_ips), len(self._dup_hostnames),
        )

    def is_ambiguous(self, token: str) -> bool:
        """Token, OsEnvanter'da birden fazla kez geçen (belirsiz) bir IP/hostname mi?"""
        token = (token or "").strip()
        if not token:
            return False
        if looks_like_ip(token):
            return token in self._dup_ips
        return token.lower() in self._dup_hostnames

    def find(self, token: str) -> Optional[OsRecord]:
        """
        remoteMachines'ten gelen tek bir değeri arar.

        IP gibi görünüyorsa önce IP indeksinde, değilse hostname indeksinde arar.
        Bulamazsa diğer indekste de bir kez daha dener (yedek strateji).
        """
        token = token.strip()
        if not token:
            return None

        if looks_like_ip(token):
            rec = self._by_ip.get(token)
            if rec is None:
                # Nadir durum: IP, hostname kolonuna yazılmış olabilir.
                rec = self._by_hostname.get(token.lower())
        else:
            rec = self._by_hostname.get(token.lower())
            if rec is None:
                rec = self._by_ip.get(token)
        return rec
