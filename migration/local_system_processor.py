# -*- coding: utf-8 -*-
"""
Part 3 (LOCAL) satır işleyici: Managed System + LOCAL Managed Account (link YOK).

Domain akışından TEK farkı: managed account, domain MS (id=2) altında değil,
row'un KENDİ managed system'i altında local hesap olarak açılır ve LİNKLENMEZ.
Managed system oluşturma/eşleştirme, functional account ve password policy
çözümü domain akışıyla birebir aynıdır (SystemProcessor'dan miras alınır).
"""

from __future__ import annotations

from typing import Dict, Optional

from beyondtrust.endpoints.managed_accounts import extract_account_id
from beyondtrust.session import BeyondTrustError
from common.logging_setup import get_logger
from config import settings
from migration.managed_account import local_account
from migration.processor import FAIL, OK, RowResult
from migration.system_processor import SystemProcessor

log = get_logger("local_system_processor")


class LocalSystemProcessor(SystemProcessor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # system_id -> { account_name_lower: account_id }  (lazy yüklenir)
        self._system_accounts: Dict[int, Dict[str, int]] = {}

    # ------------------------------------------------------------------ #
    def _accounts_of_system(self, system_id: int) -> Dict[str, int]:
        """Bir managed system altındaki mevcut hesapları (lazy) indeksler."""
        if system_id not in self._system_accounts:
            index: Dict[str, int] = {}
            try:
                for acc in self.ma_api.list_by_system(system_id):
                    name = str(acc.get("AccountName") or "").strip().lower()
                    if name:
                        index.setdefault(name, extract_account_id(acc))
            except BeyondTrustError as exc:
                log.warning("Sistem %s hesapları listelenemedi: %s", system_id, exc)
            self._system_accounts[system_id] = index
        return self._system_accounts[system_id]

    # ================================================================== #
    # LOCAL Managed Account (row'un kendi sistemi altında, link yok)
    # ================================================================== #
    def ensure_local_managed_account(
        self, system_id: int, username: str, result: RowResult
    ) -> Optional[int]:
        accounts = self._accounts_of_system(system_id)
        key = username.strip().lower()

        existing_id = accounts.get(key)
        if existing_id is not None:
            result.managed_account_id = existing_id
            result.managed_account_mark = OK
            result.add_info(f"LOCAL ManagedAccount mevcut '{username}' (system={system_id}, id={existing_id})")
            log.info("LOCAL ManagedAccount mevcut: '%s' (system=%s, id=%s)", username, system_id, existing_id)
            return existing_id

        try:
            payload = local_account.build_payload(username, self.workgroup_id)
            created = self.ma_api.create(system_id, payload)
            aid = extract_account_id(created)
            accounts[key] = aid  # per-system cache güncelle
            self.tracker.record_managed_account(aid, f"{username}@system:{system_id}")
            result.managed_account_id = aid
            result.managed_account_mark = OK
            result.add_info(f"LOCAL ManagedAccount oluşturuldu '{username}' (system={system_id}, id={aid})")
            return aid
        except BeyondTrustError as exc:
            result.managed_account_mark = FAIL
            result.add_info(f"LOCAL ManagedAccount HATA '{username}' (system={system_id}): {exc}")
            log.error("LOCAL ManagedAccount oluşturulamadı '%s' (system=%s): %s", username, system_id, exc)
            return None

    # ================================================================== #
    def process_row(self, row: dict, result: RowResult) -> None:
        result.local = True  # local akış (link yok, part3_ok link aramaz)
        username = str(row.get(settings.COL_USERNAME) or "").strip()
        label = f"[Satır {result.pam_satir} | ip={result.ip_address} | os={result.os}]"

        # SIKI ZİNCİR: Part 2 başarısızsa Part 3 hiç çalışmaz.
        if not result.part2_ok():
            result.add_info("Part 2 başarısız; Part 3 (local) atlandı (sıkı zincir).")
            log.info("%s Part 2 başarısız -> Part 3 (local) atlandı.", label)
            return

        log.info("%s Part3-LOCAL işleniyor...", label)

        # 1) Managed System (domain akışıyla aynı: IP eşleştir / OS tipine göre create)
        system_id = self.ensure_managed_system(row, result)
        if result.ignored:
            log.info("%s IGNORED -> Part3 (local) durduruldu.", label)
            return
        if not system_id:
            result.add_info("ManagedSystem oluşturulamadı; LOCAL ManagedAccount atlandı (sıkı zincir).")
            log.info("%s MS başarısız -> LOCAL MA atlandı.", label)
            return

        # 2) LOCAL Managed Account — row'un KENDİ sistemi altında (link YOK)
        if not username:
            result.managed_account_mark = FAIL
            result.add_info("username boş; local managed account açılamadı.")
            log.info("%s username boş -> LOCAL MA atlandı.", label)
            return

        self.ensure_local_managed_account(system_id, username, result)

        log.info(
            "%s sonuç -> MS=%s LOCAL-MA=%s (link yok)",
            label, result.managed_system_mark, result.managed_account_mark,
        )
