# -*- coding: utf-8 -*-
"""
OS tipine göre doğru managed system payload kurucusunu seçer.

Yeni bir tip (ör. MSSQL, Oracle) eklemek için: ilgili modülü yazıp
_BUILDERS sözlüğüne bir satır eklemek yeterli (Part 4).
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from config import settings
from migration.managed_system import linux, windows

# os_type -> payload kurucu
_BUILDERS: Dict[str, Callable[[dict], dict]] = {
    "linux": linux.build_payload,
    "windows": windows.build_payload,
}


def classify_os(os_value: Optional[str]) -> Optional[str]:
    """Ham OS metnini 'linux' / 'windows' / None olarak sınıflandırır."""
    if not os_value:
        return None
    text = str(os_value).strip().lower()
    if any(k in text for k in settings.OS_WINDOWS_KEYS):
        return "windows"
    if any(k in text for k in settings.OS_LINUX_KEYS):
        return "linux"
    return None


def build_payload(
    os_value: Optional[str],
    row: dict,
    functional_account_id: Optional[int] = None,
    password_rule_id: Optional[int] = None,
) -> Optional[dict]:
    """OS tipine göre payload üretir; tip tanınmazsa None döner.

    functional_account_id verilirse FunctionalAccountID, password_rule_id
    verilirse (0 dahil) PasswordRuleID olarak payload'a işlenir.
    """
    os_type = classify_os(os_value)
    if os_type is None:
        return None
    return _BUILDERS[os_type](row, functional_account_id, password_rule_id)
