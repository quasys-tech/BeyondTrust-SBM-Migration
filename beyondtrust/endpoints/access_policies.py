# -*- coding: utf-8 -*-
"""
AccessPolicies REST endpoint sarmalayıcısı.

Access policy'ler ad ile seçilip role atamasında AccessPolicyID olarak kullanılır.
  GET /AccessPolicies  -> liste (alanlar: AccessPolicyID, Name, ...)

Ad -> id eşleşmesi migration katmanında (cache "Name" indeksi) yapılır.
"""

from __future__ import annotations

from typing import List, Optional

from beyondtrust.session import BeyondTrustError, BeyondTrustSession
from common.logging_setup import get_logger

log = get_logger("bt.access_policies")


def extract_access_policy_id(item: dict) -> Optional[int]:
    for key in ("AccessPolicyID", "ID", "Id"):
        if item.get(key) not in (None, ""):
            value = item[key]
            return int(value) if str(value).isdigit() else value
    return None


class AccessPoliciesApi:
    def __init__(self, session: BeyondTrustSession):
        self.session = session

    def list(self) -> List[dict]:
        resp = self.session.get("/AccessPolicies")
        if resp.status_code != 200:
            raise BeyondTrustError(
                f"AccessPolicies listelenemedi: HTTP {resp.status_code} - {resp.text[:200]}"
            )
        policies = resp.json() or []
        log.info("AccessPolicies listelendi: %d kayıt.", len(policies))
        return policies
