# -*- coding: utf-8 -*-
"""
Korelasyon (correlation) motoru — Part 1'in kalbi.

PamEnvanter satırlarını OsEnvanter ile eşleştirir ve iki çıktı üretir:
  * working_rows  -> başarıyla eşleşen ve OS bilgisi olan satırlar
  * ignored_rows  -> eşleşmeyen veya OS bilgisi olmayan satırlar (+ sebep)

Uygulanan kurallar:
  1. remoteMachines, ayırıcı (';') ile parçalanır; her parça ayrı işlenir.
  2. Her parça OsEnvanter'da (IP veya hostname) aranır.
  3. Eşleşme yoksa            -> Ignored (INFO: "OsEnvanter'da eşleşme yok").
  4. Eşleşti ama OS boşsa     -> Ignored (INFO: "OS bilgisi bulunamadı").
  5. Domain boşsa            -> DEFAULT_DOMAIN kullanılır (working satırı üretilir).
  6. Hostname boşsa          -> (ayar açıksa) hostname yerine IP yazılır.
  7. IP boşsa               -> Part 2'de nslookup ile çözülecek; şimdilik boş.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from config import settings
from common.logging_setup import get_logger
from correlation.models import IgnoredRow, OsRecord, PamRow, WorkingRow
from correlation.os_inventory import OsInventory, looks_like_ip

log = get_logger("correlator")


@dataclass
class CorrelationResult:
    """Korelasyon çıktısı + sayaçlar (özet rapor için)."""

    working_rows: List[WorkingRow] = field(default_factory=list)
    ignored_rows: List[IgnoredRow] = field(default_factory=list)

    pam_rows_total: int = 0
    pam_rows_without_remote: int = 0
    remote_items_total: int = 0
    matched_items: int = 0
    ignored_no_match: int = 0
    ignored_no_os: int = 0
    ignored_duplicate: int = 0
    default_domain_used: int = 0


class Correlator:
    def __init__(self, inventory: OsInventory, default_domain: str = None):
        self.inventory = inventory
        self.default_domain = default_domain or settings.DEFAULT_DOMAIN

    def correlate(self, pam_rows: List[PamRow]) -> CorrelationResult:
        result = CorrelationResult()
        result.pam_rows_total = len(pam_rows)

        log.info("Korelasyon başlıyor: %d PamEnvanter satırı.", len(pam_rows))

        for pam in pam_rows:
            self._process_pam_row(pam, result)

        log.info(
            "Korelasyon bitti -> %d working satırı, %d ignored satırı.",
            len(result.working_rows),
            len(result.ignored_rows),
        )
        return result

    # ------------------------------------------------------------------ #
    def _process_pam_row(self, pam: PamRow, result: CorrelationResult) -> None:
        label = f"[Pam satır {pam.pam_satir} | user={pam.username} | safe={pam.safe_name}]"

        if not pam.remote_machines:
            result.pam_rows_without_remote += 1
            log.debug("%s remoteMachines boş -> atlandı.", label)
            return

        tokens = [
            t.strip()
            for t in pam.remote_machines.split(settings.REMOTE_MACHINES_SEPARATOR)
            if t.strip()
        ]
        log.info("%s %d remoteMachines değeri işleniyor.", label, len(tokens))

        for token in tokens:
            result.remote_items_total += 1
            self._process_token(pam, token, result, label)

    # ------------------------------------------------------------------ #
    def _process_token(
        self, pam: PamRow, token: str, result: CorrelationResult, label: str
    ) -> None:
        is_ip = looks_like_ip(token)
        rec = self.inventory.find(token)

        # --- Kural 3: eşleşme yok -> ignored ---
        if rec is None:
            result.ignored_no_match += 1
            ignored = IgnoredRow(
                pam_satir=pam.pam_satir,
                username=pam.username,
                safe_name=pam.safe_name,
                ip_address=token if is_ip else "",
                hostname="" if is_ip else token,
                domain="",
                os="",
                info=f"OsEnvanter'da '{token}' icin eslesme bulunamadi.",
            )
            result.ignored_rows.append(ignored)
            log.warning("%s '%s' -> IGNORED (OsEnvanter'da yok).", label, token)
            return

        # --- Belirsizlik: OsEnvanter'da token birden fazla kez var -> ignored ---
        if self.inventory.is_ambiguous(token):
            result.ignored_duplicate += 1
            ignored = IgnoredRow(
                pam_satir=pam.pam_satir,
                username=pam.username,
                safe_name=pam.safe_name,
                ip_address=token if is_ip else (rec.ip_address or ""),
                hostname=(rec.hostname or "") if is_ip else token,
                domain=rec.domain or "",
                os=rec.os or "",
                info=f"OsEnvanter'da '{token}' birden fazla kez var (belirsiz). Kontrol edin.",
            )
            result.ignored_rows.append(ignored)
            log.warning("%s '%s' -> IGNORED (OsEnvanter'da belirsiz/duplicate).", label, token)
            return

        # --- Kural 4: OS bilgisi boş -> ignored ---
        if not rec.os:
            result.ignored_no_os += 1
            ignored = IgnoredRow(
                pam_satir=pam.pam_satir,
                username=pam.username,
                safe_name=pam.safe_name,
                ip_address=rec.ip_address or (token if is_ip else ""),
                hostname=rec.hostname or ("" if is_ip else token),
                domain=rec.domain or "",
                os="",
                info=f"'{token}' eslesti ancak OS bilgisi bos -> ignore.",
            )
            result.ignored_rows.append(ignored)
            log.warning("%s '%s' -> IGNORED (OS bos).", label, token)
            return

        # --- Eşleşti ve OS var: working satırı üret ---
        ip_value = rec.ip_address or ""

        # Kural 6: hostname boşsa IP'yi hostname olarak kullan.
        hostname_value = rec.hostname
        if not hostname_value:
            if settings.HOSTNAME_FALLBACK_TO_IP and ip_value:
                hostname_value = ip_value
                log.debug(
                    "%s '%s' -> hostname bos, IP (%s) hostname olarak kullanildi.",
                    label,
                    token,
                    ip_value,
                )
            else:
                hostname_value = token

        # Kural 5: domain boşsa DEFAULT_DOMAIN.
        if rec.domain:
            domain_value = rec.domain
        else:
            domain_value = self.default_domain
            result.default_domain_used += 1
            log.warning(
                "%s '%s' -> domain bos, DEFAULT_DOMAIN (%s) kullanildi.",
                label,
                token,
                domain_value,
            )

        working = WorkingRow(
            pam_satir=pam.pam_satir,
            username=pam.username,
            ip_address=ip_value,
            hostname=hostname_value,
            os=rec.os,
            safe_name=pam.safe_name,
            domain=domain_value,
            account_type=pam.account_type,
        )
        result.working_rows.append(working)
        result.matched_items += 1
        log.info(
            "%s '%s' -> WORKING (ip=%s, host=%s, os=%s, domain=%s).",
            label,
            token,
            ip_value or "-",
            hostname_value,
            rec.os,
            domain_value,
        )
