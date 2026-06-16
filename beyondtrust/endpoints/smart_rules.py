# -*- coding: utf-8 -*-
"""
SmartRule / QuickRule REST endpoint sarmalayıcısı.

Managed account tabanlı "Quick Rule" (smart group) işlemleri:
  GET  /SmartRules                              -> tüm smart rule'lar (Title eşleşme)
  POST /QuickRules                              -> quick rule oluştur
  GET  /QuickRules/{id}/ManagedAccounts         -> kuraldaki hesap id'leri
  PUT  /QuickRules/{id}/ManagedAccounts         -> hesap listesini güncelle
  DELETE /SmartRules/{id}                       -> sil (cleanup)

Sorumluluk: sadece HTTP + yanıt çözümleme. İş kuralları migration katmanında.
"""

from __future__ import annotations

from typing import List, Optional

from beyondtrust.session import BeyondTrustError, BeyondTrustSession
from common.logging_setup import get_logger

log = get_logger("bt.smart_rules")


def extract_smart_rule_id(item: dict) -> Optional[int]:
    for key in ("SmartRuleID", "ID", "Id"):
        if item.get(key) not in (None, ""):
            value = item[key]
            return int(value) if str(value).isdigit() else value
    return None


class SmartRulesApi:
    def __init__(self, session: BeyondTrustSession):
        self.session = session

    def list(self) -> List[dict]:
        resp = self.session.get("/SmartRules")
        if resp.status_code != 200:
            raise BeyondTrustError(
                f"SmartRules listelenemedi: HTTP {resp.status_code} - {resp.text[:200]}"
            )
        rules = resp.json() or []
        log.info("SmartRules listelendi: %d kayıt.", len(rules))
        return rules

    def create_quick_rule(self, payload: dict) -> dict:
        resp = self.session.post("/QuickRules", json=payload)
        if resp.status_code not in (200, 201):
            raise BeyondTrustError(
                f"QuickRule oluşturulamadı (title={payload.get('Title')}): "
                f"HTTP {resp.status_code} - {resp.text[:300]}"
            )
        created = resp.json()
        srid = extract_smart_rule_id(created)
        log.info("QuickRule oluşturuldu: title=%s (SmartRuleID=%s)", payload.get("Title"), srid)
        return created

    def get_account_ids(self, smart_rule_id: int) -> List[int]:
        resp = self.session.get(f"/QuickRules/{smart_rule_id}/ManagedAccounts")
        if resp.status_code != 200:
            raise BeyondTrustError(
                f"QuickRule hesapları alınamadı (id={smart_rule_id}): "
                f"HTTP {resp.status_code} - {resp.text[:200]}"
            )
        accounts = resp.json() or []
        return [a.get("ManagedAccountID") for a in accounts if a.get("ManagedAccountID") is not None]

    def update_account_ids(self, smart_rule_id: int, account_ids: List[int]) -> bool:
        payload = {"AccountIDs": list(dict.fromkeys(account_ids))}  # tekilleştir, sırayı koru
        resp = self.session.put(
            f"/QuickRules/{smart_rule_id}/ManagedAccounts", json=payload
        )
        if resp.status_code not in (200, 201, 204):
            raise BeyondTrustError(
                f"QuickRule hesapları güncellenemedi (id={smart_rule_id}): "
                f"HTTP {resp.status_code} - {resp.text[:300]}"
            )
        log.info("QuickRule güncellendi: id=%s, AccountIDs=%s", smart_rule_id, payload["AccountIDs"])
        return True

    def delete(self, smart_rule_id: int) -> bool:
        resp = self.session.delete(f"/SmartRules/{smart_rule_id}")
        ok = resp.status_code in (200, 204)
        if ok:
            log.info("SmartRule silindi: ID=%s", smart_rule_id)
        else:
            log.warning(
                "SmartRule silinemedi: ID=%s HTTP %s - %s",
                smart_rule_id, resp.status_code, resp.text[:200],
            )
        return ok
