# -*- coding: utf-8 -*-
"""
ManagedAccounts REST endpoint sarmalayıcısı.

Managed account'lar bir managed system altında oluşturulur:
  GET/POST /ManagedSystems/{systemId}/ManagedAccounts
  DELETE   /ManagedAccounts/{accountId}
"""

from __future__ import annotations

from typing import List, Optional

from beyondtrust.session import BeyondTrustError, BeyondTrustSession
from common.logging_setup import get_logger

log = get_logger("bt.managed_accounts")


def extract_account_id(item: dict) -> Optional[int]:
    for key in ("ManagedAccountID", "AccountID", "ID", "Id"):
        if item.get(key) not in (None, ""):
            value = item[key]
            return int(value) if str(value).isdigit() else value
    return None


class ManagedAccountsApi:
    def __init__(self, session: BeyondTrustSession):
        self.session = session

    def list_by_system(self, system_id: int) -> List[dict]:
        resp = self.session.get(f"/ManagedSystems/{system_id}/ManagedAccounts")
        if resp.status_code != 200:
            raise BeyondTrustError(
                f"ManagedAccounts listelenemedi (system={system_id}): "
                f"HTTP {resp.status_code} - {resp.text[:200]}"
            )
        accounts = resp.json() or []
        log.info("ManagedAccounts (system=%s) listelendi: %d kayıt.", system_id, len(accounts))
        return accounts

    def create(self, system_id: int, payload: dict) -> dict:
        # Parolayı loglamadan göster.
        safe = {**payload, "Password": "***"}
        log.debug("ManagedAccount create (system=%s) payload: %s", system_id, safe)
        resp = self.session.post(
            f"/ManagedSystems/{system_id}/ManagedAccounts", json=payload
        )
        if resp.status_code not in (200, 201):
            raise BeyondTrustError(
                f"ManagedAccount '{payload.get('AccountName')}' oluşturulamadı: "
                f"HTTP {resp.status_code} - {resp.text[:300]}"
            )
        created = resp.json()
        aid = extract_account_id(created)
        log.info(
            "ManagedAccount oluşturuldu: %s (ID=%s, system=%s)",
            payload.get("AccountName"), aid, system_id,
        )
        return created

    def delete(self, account_id: int) -> bool:
        resp = self.session.delete(f"/ManagedAccounts/{account_id}")
        ok = resp.status_code in (200, 204)
        if ok:
            log.info("ManagedAccount silindi: ID=%s", account_id)
        else:
            log.warning(
                "ManagedAccount silinemedi: ID=%s HTTP %s - %s",
                account_id, resp.status_code, resp.text[:200],
            )
        return ok
