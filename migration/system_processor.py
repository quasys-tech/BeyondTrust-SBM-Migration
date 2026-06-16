# -*- coding: utf-8 -*-
"""
Part 3 satır işleyici: Managed System + Managed Account + Link.

Her working satırı için:
  1. ManagedSystem: IP (unique) ile ara.
       - IP var + hostname eşleşiyor  -> mevcut id kullan
       - IP var + hostname uyuşmuyor   -> IGNORED (sayfa + mesaj), dur
       - IP yok (eşleşme yok)          -> OS tipine göre create
  2. ManagedAccount: row'daki username'i domain managed system altında aç
       (domain MS, HostName/SystemName == DOMAIN_MANAGED_SYSTEM_NAME).
  3. Link: oluşturulan managed account'u row'un managed system'ine bağla.

Cache sayesinde aynı IP/username için tekrar create denenmez.
"""

from __future__ import annotations

from typing import Optional, Set, Tuple

from beyondtrust.cache import BeyondTrustCache
from beyondtrust.endpoints.functional_accounts import extract_functional_account_id
from beyondtrust.endpoints.managed_accounts import ManagedAccountsApi, extract_account_id
from beyondtrust.endpoints.managed_systems import ManagedSystemsApi, extract_system_id
from beyondtrust.endpoints.password_rules import extract_password_rule_id
from beyondtrust.session import BeyondTrustError
from common.logging_setup import get_logger
from config import settings
from migration.managed_account import ad_account
from migration.managed_system import factory
from migration.object_tracker import ObjectTracker
from migration.processor import FAIL, OK, RowResult

log = get_logger("system_processor")

CACHE_MANAGED_SYSTEM = "ManagedSystem"
CACHE_DOMAIN_ACCOUNT = "DomainManagedAccount"
CACHE_FUNCTIONAL_ACCOUNT = "FunctionalAccount"
CACHE_PASSWORD_RULE = "PasswordRule"


class SystemProcessor:
    def __init__(
        self,
        cache: BeyondTrustCache,
        ms_api: ManagedSystemsApi,
        ma_api: ManagedAccountsApi,
        tracker: ObjectTracker,
        workgroup_id: int,
    ):
        self.cache = cache
        self.ms_api = ms_api
        self.ma_api = ma_api
        self.tracker = tracker
        self.workgroup_id = workgroup_id  # WORKGROUP_NAME -> id (runtime'da çözüldü)
        self._link_done: Set[Tuple[int, int]] = set()
        self._domain_ms_id: Optional[int] = None
        self._functional_account_ids: dict = {}  # os_type -> FunctionalAccountID
        self._password_rule_ids: dict = {}        # os_type -> PasswordRuleID

    # ------------------------------------------------------------------ #
    def domain_system_id(self) -> Optional[int]:
        """Domain (directory) managed system id'sini ad ile çözer ve önbelleğe alır."""
        if self._domain_ms_id is None:
            dm = self.cache.get(CACHE_MANAGED_SYSTEM, "name", settings.DOMAIN_MANAGED_SYSTEM_NAME)
            if dm:
                self._domain_ms_id = extract_system_id(dm)
                log.info(
                    "Domain managed system bulundu: '%s' (id=%s)",
                    settings.DOMAIN_MANAGED_SYSTEM_NAME, self._domain_ms_id,
                )
            else:
                log.error(
                    "Domain managed system bulunamadı: '%s'",
                    settings.DOMAIN_MANAGED_SYSTEM_NAME,
                )
        return self._domain_ms_id

    def functional_account_id(self, os_type: str) -> Optional[int]:
        """OS tipi için functional account adını (settings) ID'ye çözer, önbelleğe alır.

        Bulunamazsa None döner; sistem fonksiyonel hesapsız (unmanaged) oluşturulur.
        """
        if not settings.FUNCTIONAL_ACCOUNT_USAGE:
            return None

        if os_type in self._functional_account_ids:
            return self._functional_account_ids[os_type]

        name = settings.FUNCTIONAL_ACCOUNT_NAMES.get(os_type)
        fid: Optional[int] = None
        if name:
            rec = (
                self.cache.get(CACHE_FUNCTIONAL_ACCOUNT, "name", name)
                or self.cache.get(CACHE_FUNCTIONAL_ACCOUNT, "display", name)
            )
            if rec:
                fid = extract_functional_account_id(rec)
                log.info("Functional account çözüldü [%s]: '%s' (id=%s)", os_type, name, fid)
                if fid is not None and not settings.AUTO_MANAGEMENT:
                    log.warning(
                        "FUNCTIONAL_ACCOUNT_USAGE açık ama AUTO_MANAGEMENT kapalı: "
                        "BeyondTrust FunctionalAccountID'yi kabul etmez (kayıtta None kalır). "
                        "Functional account'un yapışması için AUTO_MANAGEMENT=True yapın."
                    )
            else:
                log.warning(
                    "Functional account bulunamadı [%s]: '%s' -> sistem fonksiyonel hesapsız oluşturulacak.",
                    os_type, name,
                )
        self._functional_account_ids[os_type] = fid
        return fid

    def password_rule_id(self, os_type: str) -> Optional[int]:
        """OS tipi için password policy adını (settings) PasswordRuleID'ye çözer.

        NOT: 0 ("Default Password Policy") geçerli bir id. Bulunamazsa None döner
        ve template'teki varsayılan kullanılır.
        """
        if os_type in self._password_rule_ids:
            return self._password_rule_ids[os_type]

        name = settings.PASSWORD_POLICY_NAMES.get(os_type)
        pid: Optional[int] = None
        if name:
            rec = self.cache.get(CACHE_PASSWORD_RULE, "name", name)
            if rec:
                pid = extract_password_rule_id(rec)
                log.info("Password policy çözüldü [%s]: '%s' (PasswordRuleID=%s)", os_type, name, pid)
            else:
                log.warning(
                    "Password policy bulunamadı [%s]: '%s' -> template varsayılanı kullanılacak.",
                    os_type, name,
                )
        self._password_rule_ids[os_type] = pid
        return pid

    @staticmethod
    def _hostname_matches(ms: dict, hostname: str) -> bool:
        """Mevcut managed system'in adlarından biri row hostname'i ile eşleşiyor mu?"""
        if not hostname:
            return True  # hostname yoksa engelleme yapma
        target = hostname.strip().lower()
        for field in ("HostName", "SystemName", "DnsName"):
            if (ms.get(field) or "").strip().lower() == target:
                return True
        return False

    # ================================================================== #
    # Adım 1: Managed System
    # ================================================================== #
    def ensure_managed_system(self, row: dict, result: RowResult) -> Optional[int]:
        ip = str(row.get("ip address") or "").strip()
        hostname = str(row.get("hostname") or "").strip()
        os_value = row.get("OS")

        existing = self.cache.get(CACHE_MANAGED_SYSTEM, "ip", ip) if ip else None
        if existing:
            if self._hostname_matches(existing, hostname):
                sid = extract_system_id(existing)
                result.managed_system_id = sid
                result.managed_system_mark = OK
                result.add_info(f"ManagedSystem mevcut ip={ip} (id={sid})")
                log.info("ManagedSystem mevcut: ip=%s host=%s (id=%s)", ip, hostname, sid)
                return sid
            # IP var ama hostname uyuşmuyor -> IGNORED
            existing_host = existing.get("HostName") or existing.get("SystemName")
            result.managed_system_mark = FAIL
            result.ignored = True
            result.ignored_reason = (
                f"IP ({ip}) mevcut sistemde '{existing_host}' ile kayıtlı, "
                f"OsEnvanter hostname '{hostname}' ile eşleşmiyor. Kontrol edin."
            )
            result.add_info(result.ignored_reason)
            log.warning("[ip=%s] hostname uyuşmazlığı -> IGNORED (%s != %s)",
                        ip, existing_host, hostname)
            return None

        # IP eşleşmesi yok -> OS tipine göre create
        os_type = factory.classify_os(os_value)
        if os_type is None:
            result.managed_system_mark = FAIL
            result.ignored = True
            result.ignored_reason = f"OS tipi tanınmadı ('{os_value}'); managed system oluşturulamadı."
            result.add_info(result.ignored_reason)
            log.warning("[ip=%s] OS tipi tanınmadı: %s", ip, os_value)
            return None

        fa_id = self.functional_account_id(os_type)
        pr_id = self.password_rule_id(os_type)
        payload = factory.build_payload(
            os_value, row, functional_account_id=fa_id, password_rule_id=pr_id
        )

        try:
            created = self.ms_api.create(self.workgroup_id, payload)
            sid = extract_system_id(created)
            self.cache.add(CACHE_MANAGED_SYSTEM, created)
            self.tracker.record_managed_system(sid, hostname or ip)
            result.managed_system_id = sid
            result.managed_system_mark = OK
            result.add_info(f"ManagedSystem oluşturuldu host={hostname or ip} (id={sid})")
            return sid
        except BeyondTrustError as exc:
            result.managed_system_mark = FAIL
            result.add_info(f"ManagedSystem HATA: {exc}")
            log.error("ManagedSystem oluşturulamadı ip=%s: %s", ip, exc)
            return None

    # ================================================================== #
    # Adım 2: Managed Account (domain MS altında)
    # ================================================================== #
    def ensure_managed_account(self, username: str, domain: str, result: RowResult) -> Optional[int]:
        did = self.domain_system_id()
        if not did:
            result.managed_account_mark = FAIL
            result.add_info("Domain managed system bulunamadı; managed account açılamadı.")
            return None

        existing = self.cache.get(
            CACHE_DOMAIN_ACCOUNT, "name_domain", ad_account.account_key(username, domain)
        )
        if existing:
            aid = extract_account_id(existing)
            result.managed_account_id = aid
            result.managed_account_mark = OK
            result.add_info(f"ManagedAccount mevcut '{username}@{ad_account.normalize_domain(domain)}' (id={aid})")
            log.info("ManagedAccount mevcut: '%s@%s' (id=%s)", username, ad_account.normalize_domain(domain), aid)
            return aid

        try:
            payload = ad_account.build_payload(username, domain, self.workgroup_id)
            created = self.ma_api.create(did, payload)
            aid = extract_account_id(created)
            self.cache.add(CACHE_DOMAIN_ACCOUNT, created)
            self.tracker.record_managed_account(aid, username)
            result.managed_account_id = aid
            result.managed_account_mark = OK
            result.add_info(f"ManagedAccount oluşturuldu '{username}' (id={aid})")
            return aid
        except BeyondTrustError as exc:
            result.managed_account_mark = FAIL
            result.add_info(f"ManagedAccount HATA '{username}': {exc}")
            log.error("ManagedAccount oluşturulamadı '%s': %s", username, exc)
            return None

    # ================================================================== #
    # Adım 3: Link (account -> system)
    # ================================================================== #
    def ensure_link(self, system_id: int, account_id: int, result: RowResult) -> None:
        pair = (system_id, account_id)
        if pair in self._link_done:
            result.link_mark = OK
            result.add_info("Link bu çalışmada zaten yapıldı")
            return
        try:
            self.ms_api.link_account(system_id, account_id)
            self.tracker.record_link(system_id, account_id)
            self._link_done.add(pair)
            result.link_mark = OK
            result.add_info(f"Link tamam (account={account_id} -> system={system_id})")
        except BeyondTrustError as exc:
            result.link_mark = FAIL
            result.add_info(f"Link HATA: {exc}")
            log.error("Link eklenemedi system=%s account=%s: %s", system_id, account_id, exc)

    # ================================================================== #
    def process_row(self, row: dict, result: RowResult) -> None:
        username = str(row.get(settings.COL_USERNAME) or "").strip()
        domain = str(row.get(settings.COL_DOMAIN) or "").strip()
        label = f"[Satır {result.pam_satir} | ip={result.ip_address} | os={result.os}]"

        # SIKI ZİNCİR: Part 2 (UG+User+Member) başarısızsa Part 3 hiç çalışmaz.
        if not result.part2_ok():
            result.add_info("Part 2 başarısız; Part 3 atlandı (sıkı zincir).")
            log.info("%s Part 2 başarısız -> Part 3 atlandı.", label)
            return

        log.info("%s Part3 işleniyor...", label)

        # 1) Managed System
        system_id = self.ensure_managed_system(row, result)
        if result.ignored:
            log.info("%s IGNORED -> Part3 durduruldu.", label)
            return
        if not system_id:
            # SIKI ZİNCİR: MS oluşturulamadıysa MA/Link açma (orphan üretme).
            result.add_info("ManagedSystem oluşturulamadı; ManagedAccount/Link atlandı (sıkı zincir).")
            log.info("%s MS başarısız -> MA/Link atlandı.", label)
            return

        # 2) Managed Account
        if not username:
            result.managed_account_mark = FAIL
            result.add_info("username boş; managed account açılamadı.")
            log.info("%s username boş -> MA/Link atlandı.", label)
            return
        account_id = self.ensure_managed_account(username, domain, result)

        # 3) Link (account hazırsa)
        if account_id:
            self.ensure_link(system_id, account_id, result)
        else:
            result.add_info("ManagedAccount açılamadı; Link atlandı.")

        log.info(
            "%s sonuç -> MS=%s MA=%s Link=%s",
            label, result.managed_system_mark, result.managed_account_mark, result.link_mark,
        )
