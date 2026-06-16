# -*- coding: utf-8 -*-
"""
FunctionalAccounts REST endpoint sarmalayıcısı.

Functional account, managed system'lerin parolasını değiştirmek/yönetmek için
kullanılan yönetici hesabıdır. Managed system oluşturulurken FunctionalAccountID
ile referans verilir. Burada sadece listeleme yapılır; ada göre ID çözümü
migration katmanında (cache üzerinden) yapılır.

  GET /FunctionalAccounts
"""

from __future__ import annotations

from typing import List, Optional

from beyondtrust.session import BeyondTrustError, BeyondTrustSession
from common.logging_setup import get_logger

log = get_logger("bt.functional_accounts")


def extract_functional_account_id(item: dict) -> Optional[int]:
    for key in ("FunctionalAccountID", "ID", "Id"):
        if item.get(key) not in (None, ""):
            value = item[key]
            return int(value) if str(value).isdigit() else value
    return None


class FunctionalAccountsApi:
    def __init__(self, session: BeyondTrustSession):
        self.session = session

    def list(self) -> List[dict]:
        resp = self.session.get("/FunctionalAccounts")
        if resp.status_code != 200:
            raise BeyondTrustError(
                f"FunctionalAccounts listelenemedi: HTTP {resp.status_code} - {resp.text[:200]}"
            )
        accounts = resp.json() or []
        log.info("FunctionalAccounts listelendi: %d kayıt.", len(accounts))
        return accounts
