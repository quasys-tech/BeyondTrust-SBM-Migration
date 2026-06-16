# -*- coding: utf-8 -*-
"""
SBM Migration - Part 2  (BeyondTrust Password Safe)
===================================================

Akış:
  1. BeyondTrust'a authenticate olunur (SignAppin -> session cookie).
  2. UserGroup ve User cache'leri kurulur (lazy yüklenir).
  3. Working.xlsx satırları işlenir:
        safe name -> UserGroup (yoksa oluştur)
        safe name -> User      (yoksa oluştur)
        User      -> Group     (üye yap)
  4. Sonuçlar working_output.xlsx'e (✓/✗) yazılır.
  5. Oluşturulan nesneler data/generated_objects.json'a kaydedilir (delete.py için).
  6. Net özet rapor basılır.

Çalıştırma:
    python migrate.py
"""

from __future__ import annotations

import sys
import time

from beyondtrust.cache import BeyondTrustCache
from beyondtrust.endpoints.access_policies import AccessPoliciesApi
from beyondtrust.endpoints.functional_accounts import FunctionalAccountsApi
from beyondtrust.endpoints.managed_accounts import ManagedAccountsApi
from beyondtrust.endpoints.managed_systems import ManagedSystemsApi, extract_system_id
from beyondtrust.endpoints.password_rules import PasswordRulesApi
from beyondtrust.endpoints.smart_rules import SmartRulesApi
from beyondtrust.endpoints.user_groups import UserGroupsApi
from beyondtrust.endpoints.users import UsersApi
from beyondtrust.endpoints.workgroups import WorkgroupsApi
from beyondtrust.session import BeyondTrustError, BeyondTrustSession
from common.excel_utils import read_sheet_as_dicts
from common.logging_setup import get_logger, setup_logging
from config import settings
from migration import account_type
from migration.local_system_processor import LocalSystemProcessor
from migration.managed_account import ad_account
from migration.object_tracker import ObjectTracker
from migration.output_writer import write_output
from migration.processor import FAIL, OK, RowProcessor
from migration.smart_rule_processor import SmartRuleProcessor
from migration.system_processor import SystemProcessor

log = get_logger("migrate")


def _build_cache(
    ug_api: UserGroupsApi,
    users_api: UsersApi,
    ms_api: ManagedSystemsApi,
    ma_api: ManagedAccountsApi,
    fa_api: FunctionalAccountsApi,
    sr_api: SmartRulesApi,
    ap_api: AccessPoliciesApi,
    pr_api: PasswordRulesApi,
) -> BeyondTrustCache:
    """Tüm cache'leri tanımlar (lazy yüklenir)."""
    cache = BeyondTrustCache()
    cache.register(
        "UserGroup",
        loader=ug_api.list,
        key_funcs={"name": lambda g: g.get("Name")},
    )
    cache.register(
        "User",
        loader=users_api.list,
        key_funcs={"name": lambda u: u.get("UserName")},
    )
    cache.register(
        "ManagedSystem",
        loader=ms_api.list,
        key_funcs={
            "ip": lambda m: m.get("IPAddress"),
            "name": lambda m: m.get("SystemName") or m.get("HostName"),
        },
    )
    cache.register(
        "FunctionalAccount",
        loader=fa_api.list,
        key_funcs={
            "name": lambda f: f.get("AccountName"),
            "display": lambda f: f.get("DisplayName"),
        },
    )
    cache.register(
        "PasswordRule",
        loader=pr_api.list,
        key_funcs={"name": lambda p: p.get("Name")},
    )

    def _domain_account_loader():
        dm = cache.get("ManagedSystem", "name", settings.DOMAIN_MANAGED_SYSTEM_NAME)
        did = extract_system_id(dm) if dm else None
        return ma_api.list_by_system(did) if did else []

    cache.register(
        "DomainManagedAccount",
        loader=_domain_account_loader,
        key_funcs={
            "name_domain": lambda a: ad_account.account_key(
                a.get("AccountName"), a.get("DomainName")
            ),
        },
    )
    cache.register(
        "SmartRule",
        loader=sr_api.list,
        key_funcs={"title": lambda r: r.get("Title")},
    )
    cache.register(
        "AccessPolicy",
        loader=ap_api.list,
        key_funcs={"name": lambda p: p.get("Name")},
    )
    return cache


def _summary(results, elapsed, tracker, log_file) -> None:
    def cnt(attr, mark):
        return sum(1 for r in results if getattr(r, attr) == mark)

    ignored = sum(1 for r in results if r.ignored)
    local_n = sum(1 for r in results if r.local)
    ad_n = len(results) - local_n

    for line in [
        "",
        "================ ÖZET RAPOR (Part 2 + 3 + 4) ================",
        f"  İşlenen working satırı            : {len(results)}  (AD: {ad_n}, LOCAL: {local_n})",
        "  -----------------------------------------------------------",
        f"  User Group       ✓ {cnt('user_group_mark', OK):<3}  ✗ {cnt('user_group_mark', FAIL)}",
        f"  User             ✓ {cnt('user_mark', OK):<3}  ✗ {cnt('user_mark', FAIL)}",
        f"  Member           ✓ {cnt('member_mark', OK):<3}  ✗ {cnt('member_mark', FAIL)}",
        f"  Managed System   ✓ {cnt('managed_system_mark', OK):<3}  ✗ {cnt('managed_system_mark', FAIL)}",
        f"  Managed Account  ✓ {cnt('managed_account_mark', OK):<3}  ✗ {cnt('managed_account_mark', FAIL)}",
        f"  Link             ✓ {cnt('link_mark', OK):<3}  ✗ {cnt('link_mark', FAIL)}",
        f"  Smart Rule       ✓ {cnt('smart_rule_mark', OK):<3}  ✗ {cnt('smart_rule_mark', FAIL)}",
        f"  UG AccessLevel   ✓ {cnt('access_level_mark', OK):<3}  ✗ {cnt('access_level_mark', FAIL)}",
        f"  Role             ✓ {cnt('role_mark', OK):<3}  ✗ {cnt('role_mark', FAIL)}",
        f"  IGNORED (uyuşmazlık vb.)          : {ignored}",
        "  -----------------------------------------------------------",
        f"  Oluşturulan (takip)               : {tracker.summary()}",
        f"  Çıktı dosyası                     : {settings.WORKING_OUTPUT_FILE}",
        f"  Takip dosyası                     : {settings.OBJECT_TRACKER_FILE}",
        f"  Log dosyası                       : {log_file}",
        f"  Süre                              : {elapsed:.2f} sn",
        "=============================================================",
        "",
    ]:
        log.info(line)


def run() -> int:
    log_file = setup_logging(
        log_dir=settings.LOG_DIR,
        console_level=settings.CONSOLE_LOG_LEVEL,
        file_level=settings.FILE_LOG_LEVEL,
        use_color=settings.USE_COLOR,
    )
    start = time.perf_counter()

    log.info("####################################################")
    log.info("#  SBM Migration - Part 2 (BeyondTrust) başlıyor   #")
    log.info("####################################################")

    session = BeyondTrustSession(
        base_url=settings.API_BASE_URL,
        api_key=settings.API_KEY,
        runas_user=settings.RUNAS_USER,
        verify_ssl=settings.VERIFY_SSL,
        timeout=settings.HTTP_TIMEOUT_SECONDS,
        max_retries=settings.HTTP_MAX_RETRIES,
    )

    try:
        # 1) Authenticate
        session.authenticate()

        # 2) API + cache
        ug_api = UserGroupsApi(session)
        users_api = UsersApi(session)
        ms_api = ManagedSystemsApi(session)
        ma_api = ManagedAccountsApi(session)
        fa_api = FunctionalAccountsApi(session)
        sr_api = SmartRulesApi(session)
        ap_api = AccessPoliciesApi(session)
        pr_api = PasswordRulesApi(session)
        wg_api = WorkgroupsApi(session)
        cache = _build_cache(ug_api, users_api, ms_api, ma_api, fa_api, sr_api, ap_api, pr_api)
        cache.preload_all()  # UG + User + MS + DomainAccount + SmartRule + AccessPolicy + PasswordRule

        # Workgroup ADI -> ID (ad değişse de dinamik çözülür; bulunamazsa migration durur)
        workgroup_id = wg_api.resolve_id(settings.WORKGROUP_NAME)

        # 3) Working.xlsx oku
        rows = read_sheet_as_dicts(settings.WORKING_FILE, settings.WORKING_SHEET_NAME)
        if not rows:
            log.warning("Working.xlsx boş veya bulunamadı: %s", settings.WORKING_FILE)

        # 4) İşle  (Part 2: UG/User/Member  +  Part 3: MS/MA/Link)
        tracker = ObjectTracker(settings.OBJECT_TRACKER_FILE)
        processor = RowProcessor(cache, ug_api, users_api, tracker)
        system_processor = SystemProcessor(cache, ms_api, ma_api, tracker, workgroup_id)        # AD/domain
        local_processor = LocalSystemProcessor(cache, ms_api, ma_api, tracker, workgroup_id)    # LOCAL
        smart_rule_processor = SmartRuleProcessor(cache, sr_api, ug_api, ap_api, tracker)

        results = []
        for row in rows:
            result = processor.process_row(row)             # Part 2 (ortak)
            # Part 3: 'type' kolonuna göre yönlendir.
            if account_type.is_local(row.get(settings.COL_ACCOUNT_TYPE)):
                local_processor.process_row(row, result)    # LOCAL (kendi sistemi, link yok)
            else:
                system_processor.process_row(row, result)   # AD (domain MS, link)
            smart_rule_processor.process_row(row, result)   # Part 4 (ortak)
            results.append(result)

        # 5) Çıktı + cache istatistik
        write_output(settings.WORKING_OUTPUT_FILE, results,
                     settings.WORKING_OUTPUT_SHEET, settings.WORKING_OUTPUT_IGNORED_SHEET)
        cache.log_stats()

        # 6) Özet
        _summary(results, time.perf_counter() - start, tracker, log_file)
        log.info("Part 2 tamamlandı. ✔")
        return 0

    except BeyondTrustError as exc:
        log.error("BeyondTrust hatası: %s", exc)
        return 4
    except FileNotFoundError as exc:
        log.error("Dosya bulunamadı: %s", exc)
        return 2
    except Exception:  # noqa: BLE001
        log.exception("Beklenmeyen hata, çalışma durduruldu.")
        return 1
    finally:
        session.sign_out()


if __name__ == "__main__":
    sys.exit(run())
