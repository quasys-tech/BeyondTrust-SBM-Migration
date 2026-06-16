# -*- coding: utf-8 -*-
"""
Users REST endpoint sarmalayıcısı.

list / create / add_to_group / remove_from_group / delete.
Sadece HTTP + yanıt çözümleme; iş kuralları migration katmanında.
"""

from __future__ import annotations

from typing import List, Optional

from beyondtrust.session import BeyondTrustError, BeyondTrustSession
from common.logging_setup import get_logger

log = get_logger("bt.users")


def extract_user_id(item: dict) -> Optional[int]:
    for key in ("UserID", "ID", "Id"):
        if item.get(key) not in (None, ""):
            value = item[key]
            return int(value) if str(value).isdigit() else value
    return None


class UsersApi:
    def __init__(self, session: BeyondTrustSession):
        self.session = session

    def list(self) -> List[dict]:
        resp = self.session.get("/Users")
        if resp.status_code != 200:
            raise BeyondTrustError(
                f"Users listelenemedi: HTTP {resp.status_code} - {resp.text[:200]}"
            )
        users = resp.json() or []
        log.info("Users listelendi: %d kayıt.", len(users))
        return users

    def create(
        self,
        user_name: str,
        user_type: str,
        forest_name: str,
        domain_name: str,
        bind_user: str,
        bind_password: str,
        use_ssl: bool = False,
    ) -> dict:
        """Sadece UserName dışarıdan; geri kalan parametreler settings'ten gelir."""
        payload = {
            "UserType": user_type,
            "UserName": user_name,
            "ForestName": forest_name,
            "DomainName": domain_name,
            "BindUser": bind_user,
            "BindPassword": bind_password,
            "UseSSL": str(use_ssl).lower(),
        }
        # Parolayı loglamadan payload'ı göster.
        safe_payload = {**payload, "BindPassword": "***"}
        log.debug("User create payload: %s", safe_payload)

        resp = self.session.post("/Users/", json=payload)
        if resp.status_code not in (200, 201):
            raise BeyondTrustError(
                f"User '{user_name}' oluşturulamadı: "
                f"HTTP {resp.status_code} - {resp.text[:300]}"
            )
        created = resp.json()
        uid = extract_user_id(created)
        log.info("User oluşturuldu: '%s' (UserID=%s)", user_name, uid)
        created.setdefault("UserName", user_name)
        if uid is not None:
            created["UserID"] = uid
        return created

    def add_to_group(self, user_id: int, group_id: int) -> bool:
        """Kullanıcıyı gruba üye yapar (POST /Users/{uid}/UserGroups/{gid})."""
        resp = self.session.post(f"/Users/{user_id}/UserGroups/{group_id}", data="")
        if resp.status_code in (200, 201, 204):
            log.info("User %s -> Group %s üyeliği eklendi.", user_id, group_id)
            return True
        # Zaten üye ise bazı sürümler 400/409 döndürebilir.
        body = (resp.text or "").lower()
        if resp.status_code in (400, 409) and any(
            k in body for k in ("already", "exist", "duplicate")
        ):
            log.info("User %s zaten Group %s üyesi (yok sayıldı).", user_id, group_id)
            return True
        raise BeyondTrustError(
            f"User {user_id} gruba ({group_id}) eklenemedi: "
            f"HTTP {resp.status_code} - {resp.text[:200]}"
        )

    def remove_from_group(self, user_id: int, group_id: int) -> bool:
        resp = self.session.delete(f"/Users/{user_id}/UserGroups/{group_id}")
        ok = resp.status_code in (200, 204)
        if ok:
            log.info("Üyelik silindi: User %s / Group %s", user_id, group_id)
        else:
            log.warning(
                "Üyelik silinemedi: User %s / Group %s HTTP %s - %s",
                user_id, group_id, resp.status_code, resp.text[:200],
            )
        return ok

    def delete(self, user_id: int) -> bool:
        resp = self.session.delete(f"/Users/{user_id}")
        ok = resp.status_code in (200, 204)
        if ok:
            log.info("User silindi: UserID=%s", user_id)
        else:
            log.warning(
                "User silinemedi: UserID=%s HTTP %s - %s",
                user_id, resp.status_code, resp.text[:200],
            )
        return ok
