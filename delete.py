# -*- coding: utf-8 -*-
"""
TEMİZLİK BETİĞİ  (cleanup)  —  DİKKAT: yalnızca migration'ın OLUŞTURDUĞU
nesneleri siler.
=============================================================================

Bu betik `data/generated_objects.json` dosyasını okuyarak, migration sırasında
oluşturulan UserGroup / User / Membership kayıtlarını BeyondTrust'tan siler.
Var olan (preexisting) hiçbir kayda dokunmaz; çünkü yalnızca takip dosyasındaki
ID'ler işlenir.

ÖNEMLİ:
  * Bu betik migration projesinden BAĞIMSIZDIR. Hiçbir modül onu import etmez;
    silinse bile migration çalışmaya devam eder.
  * Müşteri ortamına TESLİM EDİLMEMELİDİR (yanlışlıkla veri silinmesin diye).

Silme sırası (bağımlılıklar nedeniyle):
  1) SmartRule (Quick Rule)           [Part 4]  (UG/role bağlarını da kaldırır)
  2) Link (account <-> system)        [Part 3]
  3) ManagedAccount                   [Part 3]
  4) ManagedSystem                    [Part 3]
  5) Membership (User <-> Group)      [Part 2]
  6) User                             [Part 2]
  7) UserGroup                        [Part 2]

Çalıştırma:
    python delete.py            # onay sorar
    python delete.py --yes      # onaysız siler
"""

from __future__ import annotations

import sys

from beyondtrust.endpoints.managed_accounts import ManagedAccountsApi
from beyondtrust.endpoints.managed_systems import ManagedSystemsApi
from beyondtrust.endpoints.smart_rules import SmartRulesApi
from beyondtrust.endpoints.user_groups import UserGroupsApi
from beyondtrust.endpoints.users import UsersApi
from beyondtrust.session import BeyondTrustError, BeyondTrustSession
from common.logging_setup import get_logger, setup_logging
from config import settings
from migration.object_tracker import ObjectTracker

log = get_logger("delete")


def run(auto_yes: bool = False) -> int:
    setup_logging(settings.LOG_DIR, settings.CONSOLE_LOG_LEVEL,
                  settings.FILE_LOG_LEVEL, settings.USE_COLOR)

    log.info("################ TEMİZLİK (CLEANUP) ################")
    tracker = ObjectTracker(settings.OBJECT_TRACKER_FILE)

    groups = tracker.groups()
    users = tracker.users()
    memberships = tracker.memberships()
    managed_systems = tracker.managed_systems()
    managed_accounts = tracker.managed_accounts()
    links = tracker.links()
    smart_rules = tracker.smart_rules()

    if tracker.is_empty():
        log.info("Takip dosyasında silinecek nesne yok: %s", settings.OBJECT_TRACKER_FILE)
        return 0

    log.info("Silinecek: %s", tracker.summary())
    if not auto_yes:
        answer = input("Bu nesneler BeyondTrust'tan SİLİNECEK. Onaylıyor musun? (yes/no): ")
        if answer.strip().lower() not in ("yes", "y", "evet", "e"):
            log.info("İptal edildi.")
            return 0

    session = BeyondTrustSession(
        base_url=settings.API_BASE_URL,
        api_key=settings.API_KEY,
        runas_user=settings.RUNAS_USER,
        verify_ssl=settings.VERIFY_SSL,
        timeout=settings.HTTP_TIMEOUT_SECONDS,
        max_retries=settings.HTTP_MAX_RETRIES,
    )

    failures = 0
    try:
        session.authenticate()
        ug_api = UserGroupsApi(session)
        users_api = UsersApi(session)
        ms_api = ManagedSystemsApi(session)
        ma_api = ManagedAccountsApi(session)
        sr_api = SmartRulesApi(session)

        # 1) SmartRule (Quick Rule) — UG/role bağlarını da kaldırır
        log.info("--- 1/7 Smart Rule'lar siliniyor (%d) ---", len(smart_rules))
        for sr in smart_rules:
            try:
                if not sr_api.delete(sr["id"]):
                    failures += 1
            except BeyondTrustError as exc:
                failures += 1
                log.error("SmartRule silme hatası (%s): %s", sr, exc)

        # 2) Link (unlink)
        log.info("--- 2/7 Linkler kaldırılıyor (%d) ---", len(links))
        for lk in links:
            try:
                if not ms_api.unlink_account(lk["system_id"], lk["account_id"]):
                    failures += 1
            except BeyondTrustError as exc:
                failures += 1
                log.error("Unlink hatası (%s): %s", lk, exc)

        # 3) ManagedAccount
        log.info("--- 3/7 Managed Account'lar siliniyor (%d) ---", len(managed_accounts))
        for a in managed_accounts:
            try:
                if not ma_api.delete(a["id"]):
                    failures += 1
            except BeyondTrustError as exc:
                failures += 1
                log.error("ManagedAccount silme hatası (%s): %s", a, exc)

        # 4) ManagedSystem
        log.info("--- 4/7 Managed System'ler siliniyor (%d) ---", len(managed_systems))
        for sysrec in managed_systems:
            try:
                if not ms_api.delete(sysrec["id"]):
                    failures += 1
            except BeyondTrustError as exc:
                failures += 1
                log.error("ManagedSystem silme hatası (%s): %s", sysrec, exc)

        # 5) Membership
        log.info("--- 5/7 Üyelikler siliniyor (%d) ---", len(memberships))
        for m in memberships:
            try:
                if not users_api.remove_from_group(m["user_id"], m["group_id"]):
                    failures += 1
            except BeyondTrustError as exc:
                failures += 1
                log.error("Üyelik silme hatası: %s", exc)

        # 6) User
        log.info("--- 6/7 Kullanıcılar siliniyor (%d) ---", len(users))
        for u in users:
            try:
                if not users_api.delete(u["id"]):
                    failures += 1
            except BeyondTrustError as exc:
                failures += 1
                log.error("User silme hatası (%s): %s", u, exc)

        # 7) UserGroup
        log.info("--- 7/7 Gruplar siliniyor (%d) ---", len(groups))
        for g in groups:
            try:
                if not ug_api.delete(g["id"]):
                    failures += 1
            except BeyondTrustError as exc:
                failures += 1
                log.error("UserGroup silme hatası (%s): %s", g, exc)

        if failures == 0:
            tracker.clear()
            log.info("Temizlik tamamlandı, takip dosyası sıfırlandı. ✔")
        else:
            log.warning(
                "Temizlik %d hata ile bitti. Takip dosyası KORUNDU "
                "(tekrar denenebilir).", failures,
            )
        return 0 if failures == 0 else 5

    except BeyondTrustError as exc:
        log.error("BeyondTrust hatası: %s", exc)
        return 4
    except Exception:  # noqa: BLE001
        log.exception("Beklenmeyen hata.")
        return 1
    finally:
        session.sign_out()


if __name__ == "__main__":
    auto = "--yes" in sys.argv or "-y" in sys.argv
    sys.exit(run(auto_yes=auto))
