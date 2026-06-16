# -*- coding: utf-8 -*-
"""
Workgroups REST endpoint sarmalayıcısı.

Workgroup ADI -> ID çözümü için kullanılır (managed system create
`/Workgroups/{id}/ManagedSystems` ve managed account payload'larında lazım).
  GET /Workgroups  -> liste (alanlar: ID, Name, OrganizationID)
"""

from __future__ import annotations

from typing import List, Optional

from beyondtrust.session import BeyondTrustError, BeyondTrustSession
from common.logging_setup import get_logger

log = get_logger("bt.workgroups")


def extract_workgroup_id(item: dict) -> Optional[int]:
    for key in ("WorkgroupID", "ID", "Id"):
        value = item.get(key)
        if value not in (None, ""):
            return int(value) if str(value).isdigit() else value
    return None


class WorkgroupsApi:
    def __init__(self, session: BeyondTrustSession):
        self.session = session

    def list(self) -> List[dict]:
        resp = self.session.get("/Workgroups")
        if resp.status_code != 200:
            raise BeyondTrustError(
                f"Workgroups listelenemedi: HTTP {resp.status_code} - {resp.text[:200]}"
            )
        groups = resp.json() or []
        log.info("Workgroups listelendi: %d kayıt.", len(groups))
        return groups

    def resolve_id(self, name: str) -> int:
        """Workgroup ADI'nı ID'ye çözer (büyük/küçük harf duyarsız). Bulamazsa hata."""
        target = (name or "").strip().lower()
        for w in self.list():
            if (w.get("Name") or "").strip().lower() == target:
                wid = extract_workgroup_id(w)
                log.info("Workgroup çözüldü: '%s' -> id=%s", name, wid)
                return wid
        raise BeyondTrustError(
            f"Workgroup bulunamadı: '{name}'. (settings.WORKGROUP_NAME / BT_WORKGROUP_NAME kontrol edin)"
        )
