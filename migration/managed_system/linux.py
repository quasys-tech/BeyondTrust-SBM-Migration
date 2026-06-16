# -*- coding: utf-8 -*-
"""Linux Managed System payload kurucusu."""

from __future__ import annotations

from copy import deepcopy
from typing import Optional

from config import settings

OS_TYPE = "linux"


def build_payload(
    row: dict,
    functional_account_id: Optional[int] = None,
    password_rule_id: Optional[int] = None,
) -> dict:
    """working satırından Linux managed system create payload'ı üretir."""
    payload = deepcopy(settings.LINUX_MANAGED_SYSTEM_TEMPLATE)
    hostname = str(row.get("hostname") or "").strip()
    ip = str(row.get("ip address") or "").strip()

    payload["HostName"] = hostname
    payload["DnsName"] = hostname or ip
    payload["IPAddress"] = ip
    payload["SystemName"] = hostname or ip
    payload["AutoManagementFlag"] = settings.AUTO_MANAGEMENT

    if functional_account_id is not None:
        payload["FunctionalAccountID"] = functional_account_id
    else:
        payload.pop("FunctionalAccountID", None)

    # PasswordRuleID: 0 geçerli olduğundan is not None ile kontrol; aksi halde
    # template'teki varsayılan (0) kalır.
    if password_rule_id is not None:
        payload["PasswordRuleID"] = password_rule_id
    return payload
