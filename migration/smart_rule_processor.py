# -*- coding: utf-8 -*-
"""
Part 4 satır işleyici: Smart Rule (Quick Rule) + UG yetkilendirme + Role/Access Policy.

Her working satırı için (Part 2/3 tamamlandıktan SONRA çağrılır):
  1. Smart Rule: ad = f"{SMARTRULE_MA_PREFIX}_{safe name}" (ör. SBM_MA_sbmuser1).
       - Yoksa: managed account id ile QuickRule oluştur.
       - Varsa: içindeki hesap id'lerini al, bu MA id'yi ekleyip güncelle
                (zaten varsa dokunma).
  2. UG yetkilendirme: UserGroup <-> SmartRule AccessLevel (Read/Write) ata.
  3. Role ataması: SmartRule'e rol(ler) + AccessPolicy (ada göre id'ye çözülür) ata.

Bağımlılıklar: result.user_group_id (Part 2), result.managed_account_id (Part 3),
result.safe_name. Eksikse ilgili adım atlanır.
"""

from __future__ import annotations

from typing import Optional

from beyondtrust.cache import BeyondTrustCache
from beyondtrust.endpoints.access_policies import AccessPoliciesApi, extract_access_policy_id
from beyondtrust.endpoints.smart_rules import SmartRulesApi, extract_smart_rule_id
from beyondtrust.endpoints.user_groups import UserGroupsApi
from beyondtrust.session import BeyondTrustError
from common.logging_setup import get_logger
from config import settings
from migration.object_tracker import ObjectTracker
from migration.processor import FAIL, OK, RowResult

log = get_logger("smart_rule_processor")

CACHE_SMART_RULE = "SmartRule"
CACHE_ACCESS_POLICY = "AccessPolicy"


class SmartRuleProcessor:
    def __init__(
        self,
        cache: BeyondTrustCache,
        sr_api: SmartRulesApi,
        ug_api: UserGroupsApi,
        ap_api: AccessPoliciesApi,
        tracker: ObjectTracker,
    ):
        self.cache = cache
        self.sr_api = sr_api
        self.ug_api = ug_api
        self.ap_api = ap_api
        self.tracker = tracker
        self._access_policy_id: Optional[int] = None
        self._access_policy_resolved = False

    # ------------------------------------------------------------------ #
    def access_policy_id(self) -> Optional[int]:
        """ACCESS_POLICY_NAME -> id çözer, bir kez (None olsa da) önbelleğe alır."""
        if self._access_policy_resolved:
            return self._access_policy_id

        name = (settings.ACCESS_POLICY_NAME or "").strip()
        if not name:
            log.warning("ACCESS_POLICY_NAME boş; role ataması yapılamayacak.")
        else:
            rec = self.cache.get(CACHE_ACCESS_POLICY, "name", name)
            if rec:
                self._access_policy_id = extract_access_policy_id(rec)
                log.info("Access policy çözüldü: '%s' (id=%s)", name, self._access_policy_id)
            else:
                log.warning("Access policy bulunamadı: '%s'; role ataması atlanacak.", name)
        self._access_policy_resolved = True
        return self._access_policy_id

    # ================================================================== #
    # Adım 1: Smart Rule (Quick Rule)
    # ================================================================== #
    def ensure_smart_rule(self, safe_name: str, account_id: int, result: RowResult) -> Optional[int]:
        title = f"{settings.SMARTRULE_MA_PREFIX}_{safe_name}"

        existing = self.cache.get(CACHE_SMART_RULE, "title", title)
        if existing:
            srid = extract_smart_rule_id(existing)
            try:
                current = self.sr_api.get_account_ids(srid)
                if account_id in current:
                    result.smart_rule_id = srid
                    result.smart_rule_mark = OK
                    result.add_info(f"SmartRule mevcut, hesap zaten bağlı '{title}' (id={srid})")
                    log.info("SmartRule mevcut + hesap bağlı: '%s' (id=%s)", title, srid)
                    return srid
                combined = current + [account_id]
                self.sr_api.update_account_ids(srid, combined)
                result.smart_rule_id = srid
                result.smart_rule_mark = OK
                result.add_info(f"SmartRule güncellendi, hesap eklendi '{title}' (id={srid})")
                log.info("SmartRule güncellendi (hesap eklendi): '%s' (id=%s)", title, srid)
                return srid
            except BeyondTrustError as exc:
                result.smart_rule_mark = FAIL
                result.add_info(f"SmartRule güncelleme HATA '{title}': {exc}")
                log.error("SmartRule güncellenemedi '%s': %s", title, exc)
                return None

        # Yoksa oluştur
        payload = {
            "IDs": [account_id],
            "Title": title,
            "Category": settings.SMART_RULE_CATEGORY,
            "Description": f"Quick Rule for {safe_name}",
            "RuleType": settings.SMART_RULE_TYPE,
        }
        try:
            created = self.sr_api.create_quick_rule(payload)
            srid = extract_smart_rule_id(created)
            # Cache uyumu için Title/SmartRuleID garanti.
            created.setdefault("Title", title)
            if srid is not None:
                created["SmartRuleID"] = srid
            self.cache.add(CACHE_SMART_RULE, created)
            self.tracker.record_smart_rule(srid, title)
            result.smart_rule_id = srid
            result.smart_rule_mark = OK
            result.add_info(f"SmartRule oluşturuldu '{title}' (id={srid})")
            return srid
        except BeyondTrustError as exc:
            result.smart_rule_mark = FAIL
            result.add_info(f"SmartRule oluşturma HATA '{title}': {exc}")
            log.error("SmartRule oluşturulamadı '%s': %s", title, exc)
            return None

    # ================================================================== #
    # Adım 2: UG <-> SmartRule AccessLevel
    # ================================================================== #
    def ensure_access_level(self, group_id: int, smart_rule_id: int, result: RowResult) -> bool:
        level = settings.SMART_RULE_ACCESS_LEVEL_ID
        # Precheck: zaten atanmış mı?
        for item in self.ug_api.list_smart_rules(group_id):
            rid = item.get("SmartRuleID") or item.get("ID")
            if rid == smart_rule_id and item.get("AccessLevelID") == level:
                result.access_level_mark = OK
                result.add_info("AccessLevel zaten mevcut")
                return True
        try:
            self.ug_api.set_smart_rule_access_level(group_id, smart_rule_id, level)
            result.access_level_mark = OK
            result.add_info(f"AccessLevel atandı (level={level})")
            return True
        except BeyondTrustError as exc:
            result.access_level_mark = FAIL
            result.add_info(f"AccessLevel HATA: {exc}")
            log.error("AccessLevel atanamadı group=%s rule=%s: %s", group_id, smart_rule_id, exc)
            return False

    # ================================================================== #
    # Adım 3: Role + Access Policy
    # ================================================================== #
    def ensure_roles(self, group_id: int, smart_rule_id: int, result: RowResult) -> bool:
        policy_id = self.access_policy_id()
        if policy_id is None:
            result.role_mark = FAIL
            result.add_info("Access policy çözülemedi; role ataması atlandı.")
            return False

        # Precheck: roller zaten dolu mu?
        roles = self.ug_api.get_smart_rule_roles(group_id, smart_rule_id)
        if _roles_non_empty(roles):
            result.role_mark = OK
            result.add_info("Role zaten mevcut")
            return True

        try:
            self.ug_api.assign_smart_rule_roles(
                group_id, smart_rule_id, settings.SMART_RULE_ROLE_IDS, policy_id
            )
            result.role_mark = OK
            result.add_info(
                f"Role atandı (roles={settings.SMART_RULE_ROLE_IDS}, policy={policy_id})"
            )
            return True
        except BeyondTrustError as exc:
            result.role_mark = FAIL
            result.add_info(f"Role HATA: {exc}")
            log.error("Role atanamadı group=%s rule=%s: %s", group_id, smart_rule_id, exc)
            return False

    # ================================================================== #
    def process_row(self, row: dict, result: RowResult) -> None:
        safe_name = result.safe_name
        account_id = result.managed_account_id
        group_id = result.user_group_id
        label = f"[Satır {result.pam_satir} | safe={safe_name}]"

        # SIKI ZİNCİR: Part 3 (MS+MA+Link) tam başarılı değilse Part 4 hiç çalışmaz.
        if not result.part3_ok():
            result.add_info("Part 3 tamamlanmadı; Part 4 atlandı (sıkı zincir).")
            log.info("%s Part 3 tamamlanmadı -> Part 4 atlandı.", label)
            return

        # Defansif: zincir geçtiyse bunlar dolu olmalı; yine de kontrol.
        if not (safe_name and account_id and group_id):
            result.smart_rule_mark = FAIL
            result.add_info("safe name / account / group eksik; Part 4 yapılamadı.")
            log.warning("%s eksik bağlam -> Part4 atlandı.", label)
            return

        log.info("%s Part4 işleniyor...", label)

        # 1) Smart Rule
        srid = self.ensure_smart_rule(safe_name, account_id, result)
        if not srid:
            return

        # 2) UG yetkilendirme + 3) Role (group_id varsa)
        if not group_id:
            result.access_level_mark = FAIL
            result.role_mark = FAIL
            result.add_info("UserGroup yok; yetkilendirme/role yapılamadı.")
            return

        if self.ensure_access_level(group_id, srid, result):
            self.ensure_roles(group_id, srid, result)
        else:
            result.role_mark = FAIL
            result.add_info("AccessLevel başarısız; role atlandı.")

        log.info(
            "%s sonuç -> SR=%s AccessLevel=%s Role=%s",
            label, result.smart_rule_mark, result.access_level_mark, result.role_mark,
        )


def _roles_non_empty(roles) -> bool:
    """GET Roles yanıtının 'dolu' olup olmadığını sürümden bağımsız değerlendirir."""
    if roles is None:
        return False
    if isinstance(roles, list):
        return len(roles) > 0
    if isinstance(roles, dict):
        inner = roles.get("Roles")
        if isinstance(inner, list):
            return len(inner) > 0
        return True  # beklenmeyen dict -> güvenli tarafta 'dolu' say (yanlış assign etme)
    text = str(roles).strip()
    return text not in ("", "[]")
