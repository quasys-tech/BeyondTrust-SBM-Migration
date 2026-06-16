# -*- coding: utf-8 -*-
"""
Veri modelleri (data models).

Excel'den okunan ve üretilen verileri "dict" yerine tip güvenli (typed)
dataclass'larla taşırız. Bu sayede kod okunaklı olur ve alan adları tek yerde
tanımlanır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class OsRecord:
    """OsEnvanter.xlsx içindeki tek bir satır."""

    hostname: Optional[str]
    ip_address: Optional[str]
    os: Optional[str]
    domain: Optional[str]
    source_row: int  # OsEnvanter'daki excel satır numarası (hata ayıklama için)


@dataclass
class PamRow:
    """PamEnvanter.xlsx içindeki tek bir satır (Part 1 için gerekli alanlar)."""

    pam_satir: int           # PamEnvanter'daki veri satır numarası (1'den başlar)
    username: Optional[str]
    safe_name: Optional[str]
    remote_machines: Optional[str]
    source_row: int          # Gerçek excel satır numarası (header dahil)
    account_type: Optional[str] = None  # 'local' / 'ad' (type kolonu)


@dataclass
class WorkingRow:
    """Working.xlsx 'Working' sayfasındaki tek bir korele satır."""

    pam_satir: int
    username: Optional[str]
    ip_address: str
    hostname: str
    os: str
    safe_name: Optional[str]
    domain: str
    account_type: Optional[str] = None  # 'local' / 'ad'

    def as_excel_row(self) -> list:
        """Excel'e yazılacak sıralı hücre listesi (header sırası ile aynı)."""
        return [
            self.pam_satir,
            self.username,
            self.ip_address,
            self.hostname,
            self.os,
            self.safe_name,
            self.domain,
            self.account_type,
        ]


@dataclass
class IgnoredRow:
    """Working.xlsx 'Ignored Rows' sayfasındaki, işlenemeyen satır."""

    username: Optional[str]
    safe_name: Optional[str]
    ip_address: str
    hostname: str
    domain: str
    os: str
    info: str  # Neden ignore edildiğinin açıklaması
    pam_satir: int = 0

    def as_excel_row(self) -> list:
        """Excel'e yazılacak sıralı hücre listesi (header sırası ile aynı)."""
        return [
            self.pam_satir,
            self.username,
            self.safe_name,
            self.ip_address,
            self.hostname,
            self.domain,
            self.os,
            self.info,
        ]
