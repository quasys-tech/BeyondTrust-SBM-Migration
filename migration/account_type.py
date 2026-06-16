# -*- coding: utf-8 -*-
"""
Hesap tipi sınıflandırma: bir working satırı LOCAL hesap mı yoksa AD/servis
hesabı mı? `type` kolonundaki değere bakılır (settings.LOCAL_ACCOUNT_KEYS).

LOCAL  -> managed account row'un KENDİ sistemi altında açılır, link YOK.
AD     -> managed account domain MS (id=2) altında açılır, sisteme LİNKLENİR.
"""

from __future__ import annotations

from config import settings


def is_local(value) -> bool:
    """type kolonu değeri LOCAL mı? (küçük harf/trim eşleşmesi)"""
    return str(value or "").strip().lower() in settings.LOCAL_ACCOUNT_KEYS


def label(value) -> str:
    """İnsan-okur etiket: 'LOCAL' / 'AD'."""
    return "LOCAL" if is_local(value) else "AD"
