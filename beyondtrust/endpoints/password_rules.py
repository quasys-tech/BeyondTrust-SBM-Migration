# -*- coding: utf-8 -*-
"""
PasswordRules REST endpoint sarmalayıcısı.

Password policy'ler ad ile seçilip managed system create'te PasswordRuleID
olarak kullanılır.
  GET /PasswordRules  -> liste (alanlar: PasswordRuleID, Name, ...)

NOT: "Default Password Policy" -> PasswordRuleID=0. Yani 0 GEÇERLİ bir id'dir;
çözümleme/atama kodu 0'ı "yok" saymamalıdır (is not None ile kontrol).

Ad -> id eşleşmesi migration katmanında (cache "Name" indeksi) yapılır.
"""

from __future__ import annotations

from typing import List, Optional

from beyondtrust.session import BeyondTrustError, BeyondTrustSession
from common.logging_setup import get_logger

log = get_logger("bt.password_rules")


def extract_password_rule_id(item: dict) -> Optional[int]:
    for key in ("PasswordRuleID", "ID", "Id"):
        value = item.get(key)
        if value is not None and value != "":
            return int(value) if str(value).isdigit() else value
    return None


class PasswordRulesApi:
    def __init__(self, session: BeyondTrustSession):
        self.session = session

    def list(self) -> List[dict]:
        resp = self.session.get("/PasswordRules")
        if resp.status_code != 200:
            raise BeyondTrustError(
                f"PasswordRules listelenemedi: HTTP {resp.status_code} - {resp.text[:200]}"
            )
        rules = resp.json() or []
        log.info("PasswordRules listelendi: %d kayıt.", len(rules))
        return rules
