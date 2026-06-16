# -*- coding: utf-8 -*-
"""
Oluşturulan nesnelerin (created objects) takibi.

Migration sırasında SADECE bizim oluşturduğumuz nesneler (UserGroup, User,
UserGroupMembership) bir JSON dosyasına yazılır. Ayrı `delete.py` betiği bu
dosyayı okuyarak ortamı temizler. Böylece var olan (preexisting) kayıtlara
asla dokunulmaz.

Dosya formatı:
{
  "UserGroup":            [ {"id": 18, "name": "sbmuser1"} ],
  "User":                 [ {"id": 24, "name": "sbmuser1"} ],
  "UserGroupMembership":  [ {"user_id": 24, "group_id": 18} ]
}

Not: Kayıtlar çalışmalar arası birikir (append + tekilleştirme). delete.py
temizledikten sonra clear() ile dosyayı sıfırlar.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from common.logging_setup import get_logger

log = get_logger("tracker")

KEY_GROUP = "UserGroup"
KEY_USER = "User"
KEY_MEMBERSHIP = "UserGroupMembership"
KEY_MANAGED_SYSTEM = "ManagedSystem"
KEY_MANAGED_ACCOUNT = "ManagedAccount"
KEY_LINK = "Link"
KEY_SMART_RULE = "SmartRule"

_ALL_KEYS = (
    KEY_GROUP, KEY_USER, KEY_MEMBERSHIP,
    KEY_MANAGED_SYSTEM, KEY_MANAGED_ACCOUNT, KEY_LINK,
    KEY_SMART_RULE,
)


class ObjectTracker:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: Dict[str, List[dict]] = self._load()

    # ------------------------------------------------------------------ #
    def _load(self) -> Dict[str, List[dict]]:
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                for key in _ALL_KEYS:
                    data.setdefault(key, [])
                return data
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Takip dosyası okunamadı (%s), sıfırdan başlanıyor.", exc)
        return {key: [] for key in _ALL_KEYS}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _append_unique(bucket: List[dict], item: dict) -> bool:
        if item in bucket:
            return False
        bucket.append(item)
        return True

    # ------------------------------------------------------------------ #
    def record_group(self, group_id: int, name: str) -> None:
        if group_id is None:
            return
        if self._append_unique(self.data.setdefault(KEY_GROUP, []),
                               {"id": group_id, "name": name}):
            log.debug("Takibe alındı (UserGroup): %s (id=%s)", name, group_id)
            self._save()

    def record_user(self, user_id: int, name: str) -> None:
        if user_id is None:
            return
        if self._append_unique(self.data.setdefault(KEY_USER, []),
                               {"id": user_id, "name": name}):
            log.debug("Takibe alındı (User): %s (id=%s)", name, user_id)
            self._save()

    def record_membership(self, user_id: int, group_id: int) -> None:
        if user_id is None or group_id is None:
            return
        if self._append_unique(self.data.setdefault(KEY_MEMBERSHIP, []),
                               {"user_id": user_id, "group_id": group_id}):
            log.debug("Takibe alındı (Membership): user=%s group=%s", user_id, group_id)
            self._save()

    def record_managed_system(self, system_id: int, name: str) -> None:
        if system_id is None:
            return
        if self._append_unique(self.data.setdefault(KEY_MANAGED_SYSTEM, []),
                               {"id": system_id, "name": name}):
            log.debug("Takibe alındı (ManagedSystem): %s (id=%s)", name, system_id)
            self._save()

    def record_managed_account(self, account_id: int, name: str) -> None:
        if account_id is None:
            return
        if self._append_unique(self.data.setdefault(KEY_MANAGED_ACCOUNT, []),
                               {"id": account_id, "name": name}):
            log.debug("Takibe alındı (ManagedAccount): %s (id=%s)", name, account_id)
            self._save()

    def record_link(self, system_id: int, account_id: int) -> None:
        if system_id is None or account_id is None:
            return
        if self._append_unique(self.data.setdefault(KEY_LINK, []),
                               {"system_id": system_id, "account_id": account_id}):
            log.debug("Takibe alındı (Link): system=%s account=%s", system_id, account_id)
            self._save()

    def record_smart_rule(self, smart_rule_id: int, title: str) -> None:
        if smart_rule_id is None:
            return
        if self._append_unique(self.data.setdefault(KEY_SMART_RULE, []),
                               {"id": smart_rule_id, "name": title}):
            log.debug("Takibe alındı (SmartRule): %s (id=%s)", title, smart_rule_id)
            self._save()

    # ------------------------------------------------------------------ #
    def groups(self) -> List[dict]:
        return self.data.get(KEY_GROUP, [])

    def managed_systems(self) -> List[dict]:
        return self.data.get(KEY_MANAGED_SYSTEM, [])

    def managed_accounts(self) -> List[dict]:
        return self.data.get(KEY_MANAGED_ACCOUNT, [])

    def links(self) -> List[dict]:
        return self.data.get(KEY_LINK, [])

    def users(self) -> List[dict]:
        return self.data.get(KEY_USER, [])

    def memberships(self) -> List[dict]:
        return self.data.get(KEY_MEMBERSHIP, [])

    def smart_rules(self) -> List[dict]:
        return self.data.get(KEY_SMART_RULE, [])

    def summary(self) -> str:
        return (
            f"{len(self.groups())} grup, {len(self.users())} kullanıcı, "
            f"{len(self.memberships())} üyelik, {len(self.managed_systems())} sistem, "
            f"{len(self.managed_accounts())} hesap, {len(self.links())} link, "
            f"{len(self.smart_rules())} smart rule"
        )

    def is_empty(self) -> bool:
        return not any(self.data.get(k) for k in _ALL_KEYS)

    def clear(self) -> None:
        """Temizlik sonrası takip dosyasını sıfırlar."""
        self.data = {key: [] for key in _ALL_KEYS}
        self._save()
        log.info("Takip dosyası sıfırlandı: %s", self.path)
