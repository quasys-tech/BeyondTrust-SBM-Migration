# -*- coding: utf-8 -*-
"""
Satır işleyici (row processor) — Part 2'nin kalbi.

working.xlsx'teki her satır için sırayla:
  1. safe name -> User Group var mı? Yoksa oluştur (cache + tracker güncellenir).
  2. safe name -> User var mı? Yoksa oluştur.
  3. User'ı gruba üye yap.

Her adımın sonucu işaretle (✓ başarılı / ✗ sorunlu / - atlandı) raporlanır.
Cache sayesinde aynı safe için tekrar oluşturma denemesi yapılmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Set, Tuple

from beyondtrust.endpoints.user_groups import UserGroupsApi, extract_group_id
from beyondtrust.endpoints.users import UsersApi, extract_user_id
from beyondtrust.cache import BeyondTrustCache
from beyondtrust.session import BeyondTrustError
from common.logging_setup import get_logger
from config import settings
from migration.object_tracker import ObjectTracker

log = get_logger("processor")

OK = "✓"
FAIL = "✗"
SKIP = "-"

CACHE_USER_GROUP = "UserGroup"
CACHE_USER = "User"


class Status(str, Enum):
    EXISTED = "existed"
    CREATED = "created"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class RowResult:
    """Bir working satırının işlenme sonucu (working_output.xlsx'e yazılır)."""

    pam_satir: object
    username: str
    ip_address: str
    hostname: str
    os: str
    safe_name: str
    domain: str

    user_group_mark: str = SKIP
    user_mark: str = SKIP
    member_mark: str = SKIP

    # Part 3 — Managed System / Account / Link
    managed_system_mark: str = SKIP
    managed_account_mark: str = SKIP
    link_mark: str = SKIP

    # Part 4 — Smart Rule / UG yetkilendirme / Role
    smart_rule_mark: str = SKIP
    access_level_mark: str = SKIP
    role_mark: str = SKIP

    user_group_id: Optional[int] = None
    user_id: Optional[int] = None
    managed_system_id: Optional[int] = None
    managed_account_id: Optional[int] = None
    smart_rule_id: Optional[int] = None

    # Local hesap akışı mı? (True ise managed account row'un kendi MS'inde, link yok)
    local: bool = False

    # IP/hostname uyuşmazlığı gibi durumlarda "Ignored" sayfasına taşınır.
    ignored: bool = False
    ignored_reason: str = ""

    info: str = ""

    def add_info(self, message: str) -> None:
        self.info = f"{self.info} | {message}".strip(" |") if self.info else message

    # --- Sıkı zincir (all-or-nothing) kapıları --------------------------- #
    def part2_ok(self) -> bool:
        """Part 2 (UserGroup + User + Membership) tam başarılı mı?"""
        return (
            self.user_group_mark == OK
            and self.user_mark == OK
            and self.member_mark == OK
        )

    def part3_ok(self) -> bool:
        """Part 3 tam başarılı mı? Local hesapta link yoktur; link aranmaz."""
        base = self.managed_system_mark == OK and self.managed_account_mark == OK
        if self.local:
            return base
        return base and self.link_mark == OK


class RowProcessor:
    def __init__(
        self,
        cache: BeyondTrustCache,
        user_groups_api: UserGroupsApi,
        users_api: UsersApi,
        tracker: ObjectTracker,
    ):
        self.cache = cache
        self.ug_api = user_groups_api
        self.users_api = users_api
        self.tracker = tracker
        self._membership_done: Set[Tuple[int, int]] = set()

    # ================================================================== #
    # Adım 1: User Group
    # ================================================================== #
    def ensure_user_group(self, name: str, result: RowResult) -> Optional[int]:
        existing = self.cache.get(CACHE_USER_GROUP, "name", name)
        if existing:
            gid = extract_group_id(existing)
            result.user_group_id = gid
            result.user_group_mark = OK
            result.add_info(f"UserGroup mevcut '{name}' (id={gid})")
            log.info("UserGroup mevcut: '%s' (id=%s)", name, gid)
            return gid

        try:
            created = self.ug_api.create(name, permissions=settings.USER_GROUP_PERMISSIONS,
                                         group_type=settings.USER_GROUP_TYPE)
            gid = extract_group_id(created)
            self.cache.add(CACHE_USER_GROUP, created)
            self.tracker.record_group(gid, name)
            result.user_group_id = gid
            result.user_group_mark = OK
            result.add_info(f"UserGroup oluşturuldu '{name}' (id={gid})")
            return gid
        except BeyondTrustError as exc:
            result.user_group_mark = FAIL
            result.add_info(f"UserGroup HATA '{name}': {exc}")
            log.error("UserGroup oluşturulamadı '%s': %s", name, exc)
            return None

    # ================================================================== #
    # Adım 2: User
    # ================================================================== #
    def ensure_user(self, name: str, result: RowResult) -> Optional[int]:
        existing = self.cache.get(CACHE_USER, "name", name)
        if existing:
            uid = extract_user_id(existing)
            result.user_id = uid
            result.user_mark = OK
            result.add_info(f"User mevcut '{name}' (id={uid})")
            log.info("User mevcut: '%s' (id=%s)", name, uid)
            return uid

        try:
            created = self.users_api.create(
                user_name=name,
                user_type=settings.USER_TYPE,
                forest_name=settings.AD_FOREST_NAME,
                domain_name=settings.AD_DOMAIN_NAME,
                bind_user=settings.AD_BIND_USER,
                bind_password=settings.AD_BIND_PASSWORD,
                use_ssl=settings.AD_USE_SSL,
            )
            uid = extract_user_id(created)
            self.cache.add(CACHE_USER, created)
            self.tracker.record_user(uid, name)
            result.user_id = uid
            result.user_mark = OK
            result.add_info(f"User oluşturuldu '{name}' (id={uid})")
            return uid
        except BeyondTrustError as exc:
            result.user_mark = FAIL
            msg = str(exc).lower()
            # AD'de kullanıcı yoksa bu bir IGNORE senaryosudur (hard hata değil):
            # safe name AD'de mevcut bir kullanıcı olmalı.
            if ("not found" in msg) or ("bulunamad" in msg):
                result.ignored = True
                result.ignored_reason = (
                    f"AD'de kullanıcı bulunamadı: '{name}'. "
                    f"(safe name AD'de geçerli bir kullanıcı olmalı)"
                )
                result.add_info(result.ignored_reason)
                log.warning("User AD'de yok -> IGNORED: '%s'", name)
            else:
                result.add_info(f"User HATA '{name}': {exc}")
                log.error("User oluşturulamadı '%s': %s", name, exc)
            return None

    # ================================================================== #
    # Adım 3: Üyelik (User -> Group)
    # ================================================================== #
    def ensure_membership(self, user_id: int, group_id: int, result: RowResult) -> None:
        pair = (user_id, group_id)
        if pair in self._membership_done:
            result.member_mark = OK
            result.add_info("Üyelik bu çalışmada zaten yapıldı")
            return
        try:
            self.users_api.add_to_group(user_id, group_id)
            self.tracker.record_membership(user_id, group_id)
            self._membership_done.add(pair)
            result.member_mark = OK
            result.add_info(f"Üyelik tamam (user={user_id} -> group={group_id})")
        except BeyondTrustError as exc:
            result.member_mark = FAIL
            result.add_info(f"Üyelik HATA: {exc}")
            log.error("Üyelik eklenemedi user=%s group=%s: %s", user_id, group_id, exc)

    # ================================================================== #
    def process_row(self, row: dict) -> RowResult:
        ug_name = str(row.get(settings.USER_GROUP_SOURCE_COLUMN) or "").strip()
        user_name = str(row.get(settings.USER_SOURCE_COLUMN) or "").strip()

        result = RowResult(
            pam_satir=row.get(settings.COL_PAM_SATIR),
            username=str(row.get(settings.COL_USERNAME) or ""),
            ip_address=str(row.get("ip address") or ""),
            hostname=str(row.get("hostname") or ""),
            os=str(row.get("OS") or ""),
            safe_name=ug_name,
            domain=str(row.get(settings.COL_DOMAIN) or ""),
        )

        label = f"[Satır {result.pam_satir} | safe={ug_name}]"
        log.info("%s işleniyor...", label)

        if not ug_name:
            result.user_group_mark = FAIL
            result.add_info("safe name boş; işlem yapılamadı.")
            log.warning("%s safe name boş -> atlandı.", label)
            return result

        # 1) User ÖNCE (AD doğrulaması burada olur). AD'de yoksa satır IGNORED
        #    edilir ve UserGroup HİÇ oluşturulmaz (orphan UG üretilmez).
        user_id = self.ensure_user(user_name, result)
        if result.ignored:
            log.info("%s AD kullanıcı yok -> satır IGNORED (UG/Part3/4 atlandı).", label)
            return result

        # 2) User Group
        group_id = self.ensure_user_group(ug_name, result)

        # 3) Membership (ikisi de hazırsa)
        if group_id and user_id:
            self.ensure_membership(user_id, group_id, result)
        else:
            result.member_mark = FAIL
            result.add_info("Üyelik için group/user hazır değil.")

        log.info(
            "%s sonuç -> UG=%s User=%s Member=%s",
            label, result.user_group_mark, result.user_mark, result.member_mark,
        )
        return result
