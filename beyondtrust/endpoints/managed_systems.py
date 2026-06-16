# -*- coding: utf-8 -*-
"""
ManagedSystems REST endpoint sarmalayıcısı.

Sorumluluk: sadece HTTP + yanıt çözümleme. İş kuralları migration katmanında.
"""

from __future__ import annotations

from typing import List, Optional

from beyondtrust.session import BeyondTrustError, BeyondTrustSession
from common.logging_setup import get_logger

log = get_logger("bt.managed_systems")


def extract_system_id(item: dict) -> Optional[int]:
    for key in ("ManagedSystemID", "ID", "Id"):
        if item.get(key) not in (None, ""):
            value = item[key]
            return int(value) if str(value).isdigit() else value
    return None


class ManagedSystemsApi:
    def __init__(self, session: BeyondTrustSession):
        self.session = session

    def list(self) -> List[dict]:
        resp = self.session.get("/ManagedSystems")
        if resp.status_code != 200:
            raise BeyondTrustError(
                f"ManagedSystems listelenemedi: HTTP {resp.status_code} - {resp.text[:200]}"
            )
        systems = resp.json() or []
        log.info("ManagedSystems listelendi: %d kayıt.", len(systems))
        return systems

    def create(self, workgroup_id: int, payload: dict) -> dict:
        resp = self.session.post(
            f"/Workgroups/{workgroup_id}/ManagedSystems", json=payload
        )
        if resp.status_code not in (200, 201):
            raise BeyondTrustError(
                f"ManagedSystem oluşturulamadı (host={payload.get('HostName')}): "
                f"HTTP {resp.status_code} - {resp.text[:300]}"
            )
        created = resp.json()
        sid = extract_system_id(created)
        log.info(
            "ManagedSystem oluşturuldu: host=%s ip=%s (ID=%s)",
            payload.get("HostName"), payload.get("IPAddress"), sid,
        )
        return created

    def list_linked_accounts(self, system_id: int) -> List[dict]:
        resp = self.session.get(f"/ManagedSystems/{system_id}/LinkedAccounts")
        if resp.status_code != 200:
            return []
        return resp.json() or []

    def link_account(self, system_id: int, account_id: int) -> bool:
        resp = self.session.post(
            f"/ManagedSystems/{system_id}/LinkedAccounts/{account_id}", data=""
        )
        if resp.status_code in (200, 201, 204):
            log.info("Link: account %s -> system %s", account_id, system_id)
            return True
        body = (resp.text or "").lower()
        if resp.status_code in (400, 409) and any(
            k in body for k in ("already", "exist", "duplicate", "linked")
        ):
            log.info("Link zaten var: account %s -> system %s", account_id, system_id)
            return True
        raise BeyondTrustError(
            f"Link başarısız (system={system_id}, account={account_id}): "
            f"HTTP {resp.status_code} - {resp.text[:200]}"
        )

    def unlink_account(self, system_id: int, account_id: int) -> bool:
        resp = self.session.delete(
            f"/ManagedSystems/{system_id}/LinkedAccounts/{account_id}"
        )
        ok = resp.status_code in (200, 204)
        if ok:
            log.info("Unlink: account %s -/-> system %s", account_id, system_id)
        else:
            log.warning(
                "Unlink başarısız (system=%s, account=%s): HTTP %s - %s",
                system_id, account_id, resp.status_code, resp.text[:200],
            )
        return ok

    def delete(self, system_id: int) -> bool:
        resp = self.session.delete(f"/ManagedSystems/{system_id}")
        ok = resp.status_code in (200, 204)
        if ok:
            log.info("ManagedSystem silindi: ID=%s", system_id)
        else:
            log.warning(
                "ManagedSystem silinemedi: ID=%s HTTP %s - %s",
                system_id, resp.status_code, resp.text[:200],
            )
        return ok
