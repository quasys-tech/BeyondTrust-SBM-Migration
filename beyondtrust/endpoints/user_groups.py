# -*- coding: utf-8 -*-
"""
UserGroups REST endpoint sarmalayıcısı.

Sorumluluk: sadece HTTP çağrısı + yanıt çözümleme. İş kuralları (var mı? yoksa
oluştur?) migration katmanında. ID çıkarımı sürüm farklarına dayanıklıdır.
"""

from __future__ import annotations

from typing import List, Optional

from beyondtrust.session import BeyondTrustError, BeyondTrustSession
from common.logging_setup import get_logger

log = get_logger("bt.user_groups")


def extract_group_id(item: dict) -> Optional[int]:
    """Bir user group sözlüğünden GroupID'yi sürümden bağımsız çıkarır."""
    for key in ("GroupID", "UserGroupID", "ID", "Id"):
        if item.get(key) not in (None, ""):
            value = item[key]
            return int(value) if str(value).isdigit() else value
    return None


class UserGroupsApi:
    def __init__(self, session: BeyondTrustSession):
        self.session = session

    def list(self) -> List[dict]:
        resp = self.session.get("/UserGroups")
        if resp.status_code != 200:
            raise BeyondTrustError(
                f"UserGroups listelenemedi: HTTP {resp.status_code} - {resp.text[:200]}"
            )
        groups = resp.json() or []
        log.info("UserGroups listelendi: %d kayıt.", len(groups))
        return groups

    def create(
        self,
        group_name: str,
        permissions: list,
        group_type: str = "BeyondInsight",
        description: Optional[str] = None,
    ) -> dict:
        payload = {
            "groupType": group_type,
            "groupName": group_name,
            "description": description or group_name,
            "isActive": True,
            "Permissions": permissions,
        }
        log.debug("UserGroup create payload: %s", payload)
        resp = self.session.post("/UserGroups", json=payload)
        if resp.status_code not in (200, 201):
            raise BeyondTrustError(
                f"UserGroup '{group_name}' oluşturulamadı: "
                f"HTTP {resp.status_code} - {resp.text[:300]}"
            )
        created = resp.json()
        gid = extract_group_id(created)
        log.info("UserGroup oluşturuldu: '%s' (GroupID=%s)", group_name, gid)
        # Cache ile uyum için Name/GroupID alanlarını garanti altına al.
        created.setdefault("Name", group_name)
        if gid is not None:
            created["GroupID"] = gid
        return created

    def delete(self, group_id: int) -> bool:
        resp = self.session.delete(f"/UserGroups/{group_id}")
        ok = resp.status_code in (200, 204)
        if ok:
            log.info("UserGroup silindi: GroupID=%s", group_id)
        else:
            log.warning(
                "UserGroup silinemedi: GroupID=%s HTTP %s - %s",
                group_id, resp.status_code, resp.text[:200],
            )
        return ok

    # ------------------------------------------------------------------ #
    # Part 4: UserGroup <-> SmartRule yetkilendirme (access level + role)
    # ------------------------------------------------------------------ #
    def list_smart_rules(self, group_id: int) -> List[dict]:
        """Grubun yetkili olduğu smart rule'lar (precheck için)."""
        resp = self.session.get(f"/UserGroups/{group_id}/SmartRules")
        if resp.status_code != 200:
            return []
        return resp.json() or []

    def set_smart_rule_access_level(
        self, group_id: int, smart_rule_id: int, access_level_id: int
    ) -> bool:
        """UG-SmartRule erişim seviyesi atar. Rol atamasından ÖNCE şart."""
        resp = self.session.post(
            f"/UserGroups/{group_id}/SmartRules/{smart_rule_id}/AccessLevels",
            json={"AccessLevelID": access_level_id},
        )
        if resp.status_code in (200, 201, 204):
            log.info(
                "AccessLevel atandı: group=%s rule=%s level=%s",
                group_id, smart_rule_id, access_level_id,
            )
            return True
        body = (resp.text or "").lower()
        if resp.status_code in (400, 409) and any(
            k in body for k in ("already", "exist", "duplicate")
        ):
            log.info("AccessLevel zaten var: group=%s rule=%s", group_id, smart_rule_id)
            return True
        raise BeyondTrustError(
            f"AccessLevel atanamadı (group={group_id}, rule={smart_rule_id}): "
            f"HTTP {resp.status_code} - {resp.text[:200]}"
        )

    def get_smart_rule_roles(self, group_id: int, smart_rule_id: int):
        """Grubun smart rule üzerindeki rolleri. Boşsa role ataması yapılmalı."""
        resp = self.session.get(
            f"/UserGroups/{group_id}/SmartRules/{smart_rule_id}/Roles"
        )
        if resp.status_code != 200:
            return None
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return (resp.text or "").strip()

    def assign_smart_rule_roles(
        self, group_id: int, smart_rule_id: int, role_ids: list, access_policy_id: int
    ) -> bool:
        """SmartRule'e rol(ler) + access policy atar."""
        payload = {
            "Roles": [{"RoleID": str(rid)} for rid in role_ids],
            "AccessPolicyID": str(access_policy_id),
        }
        resp = self.session.post(
            f"/UserGroups/{group_id}/SmartRules/{smart_rule_id}/Roles", json=payload
        )
        if resp.status_code in (200, 201, 204):
            log.info(
                "Role atandı: group=%s rule=%s roles=%s policy=%s",
                group_id, smart_rule_id, role_ids, access_policy_id,
            )
            return True
        body = (resp.text or "").lower()
        if resp.status_code == 400 and "accesslevel before setting roles" in body:
            raise BeyondTrustError(
                "Role atanamadı: önce UserGroup-SmartRule AccessLevel atanmalı."
            )
        if resp.status_code in (400, 409) and any(
            k in body for k in ("already", "exist", "duplicate")
        ):
            log.info("Role zaten var: group=%s rule=%s", group_id, smart_rule_id)
            return True
        raise BeyondTrustError(
            f"Role atanamadı (group={group_id}, rule={smart_rule_id}): "
            f"HTTP {resp.status_code} - {resp.text[:200]}"
        )
