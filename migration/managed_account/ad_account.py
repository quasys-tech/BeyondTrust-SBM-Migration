# -*- coding: utf-8 -*-
"""AD (ActiveDirectory) Managed Account payload kurucusu."""

from __future__ import annotations

from copy import deepcopy

from config import settings


def normalize_domain(domain: str) -> str:
    """Domain'i tek noktadan normalize eder (boşsa DEFAULT_DOMAIN)."""
    return (domain or settings.DEFAULT_DOMAIN).strip()


def account_key(account_name: str, domain: str) -> str:
    """Managed account tekil eşleşme anahtarı: AccountName + DomainName.

    Aynı isimli hesap farklı domain'lerde ayrı kabul edilir. Cache indeksi de,
    arama da bu fonksiyondan beslenir ki üretilen anahtar birebir aynı olsun.
    """
    name = (account_name or "").strip().lower()
    return f"{name}@{normalize_domain(domain).lower()}"


def build_payload(username: str, domain: str, workgroup_id: int) -> dict:
    """
    Domain managed system altında açılacak AD managed account payload'ı.

    AccountName = working satırındaki username (ör. srvsbmuser1).
    DomainName  = satırdaki domain (yoksa DEFAULT_DOMAIN).
    Parola settings'ten; workgroup_id çalışma anında ada göre çözülmüş id.
    """
    domain = normalize_domain(domain)
    payload = deepcopy(settings.MANAGED_ACCOUNT_TEMPLATE)
    payload["DomainName"] = domain
    payload["AccountName"] = username
    payload["UserPrincipalName"] = username
    payload["SAMAccountName"] = username
    payload["Password"] = settings.MANAGED_ACCOUNT_PASSWORD
    payload["WorkgroupID"] = workgroup_id
    return payload
