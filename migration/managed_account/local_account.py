# -*- coding: utf-8 -*-
"""LOCAL Managed Account payload kurucusu.

Local hesap, row'un kendi managed system'i altında açılır (domain MS değil) ve
linklenmez. Domain yoktur (DomainName="None"). Parola settings'ten gelir.
"""

from __future__ import annotations

from copy import deepcopy

from config import settings


def build_payload(username: str, workgroup_id: int, password: str = None) -> dict:
    """Local managed account create payload'ı (verilen system altında açılır)."""
    payload = deepcopy(settings.LOCAL_MANAGED_ACCOUNT_TEMPLATE)
    payload["AccountName"] = username
    payload["Password"] = password if password is not None else settings.MANAGED_ACCOUNT_PASSWORD
    payload["WorkgroupID"] = workgroup_id
    return payload
