# -*- coding: utf-8 -*-
"""
Profesyonel cache katmanı.

Her satır işlenirken tekrar tekrar UserGroup / User (Part 3'te ManagedSystem,
ManagedAccount) listelemek yerine, veriyi bir kez çekip bellekte indeksleriz.
Yeni bir nesne oluşturulduğunda cache anında güncellenir (write-through), böylece
aynı çalışma içinde tekrar oluşturma denemesi olmaz.

Tasarım:
  * EntityCache  -> tek bir varlık türü için (lazy load + çok anahtarlı indeks).
  * BeyondTrustCache -> tüm EntityCache'leri bir arada tutan yönetici.

Referans projedeki UniversalCache'e göre farklar:
  * Lazy yükleme (ilk erişimde otomatik yüklenir, manuel build_index gerekmez).
  * Büyük/küçük harf duyarsız, çok anahtarlı indeks tek yerde tanımlanır.
  * Yazma sonrası (after-create) tek 'add' çağrısıyla tüm indeksler güncellenir.
  * İstatistik (hit/miss) ile gözlemlenebilirlik.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from common.logging_setup import get_logger

log = get_logger("bt.cache")

# Bir cache kaydından, bir indeks anahtarı üreten fonksiyon tipi.
KeyFunc = Callable[[dict], Optional[str]]
# Tüm kayıtları API'den çeken yükleyici tipi.
LoaderFunc = Callable[[], List[dict]]


def _norm(value) -> Optional[str]:
    """Anahtarları normalize eder (str + trim + lower)."""
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


@dataclass
class _Stats:
    loads: int = 0
    hits: int = 0
    misses: int = 0
    adds: int = 0


@dataclass
class EntityCache:
    """Tek varlık türü için lazy yüklenen, çok anahtarlı indeksli cache."""

    name: str
    loader: LoaderFunc
    key_funcs: Dict[str, KeyFunc]  # indeks adı -> anahtar üretici

    _items: List[dict] = field(default_factory=list)
    _indexes: Dict[str, Dict[str, dict]] = field(default_factory=dict)
    _loaded: bool = False
    _stats: _Stats = field(default_factory=_Stats)

    # ------------------------------------------------------------------ #
    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        log.debug("[%s] cache yükleniyor...", self.name)
        items = self.loader() or []
        self._items = list(items)
        self._indexes = {idx: {} for idx in self.key_funcs}
        for item in self._items:
            self._index_item(item)
        self._loaded = True
        self._stats.loads += 1
        log.info("[%s] cache hazır: %d kayıt, indeksler=%s",
                 self.name, len(self._items), list(self.key_funcs))

    def reload(self) -> None:
        """Cache'i sıfırlayıp yeniden yükler."""
        self._loaded = False
        self._items.clear()
        self._indexes.clear()
        self.ensure_loaded()

    # ------------------------------------------------------------------ #
    def _index_item(self, item: dict) -> None:
        for idx, key_func in self.key_funcs.items():
            key = _norm(key_func(item))
            if key is not None:
                self._indexes.setdefault(idx, {}).setdefault(key, item)

    def get(self, index_name: str, value) -> Optional[dict]:
        """İndekslenmiş veriden arar; bulamazsa None."""
        self.ensure_loaded()
        key = _norm(value)
        if key is None:
            return None
        found = self._indexes.get(index_name, {}).get(key)
        if found is not None:
            self._stats.hits += 1
        else:
            self._stats.misses += 1
        return found

    def add(self, item: dict) -> None:
        """Yeni oluşturulan kaydı cache + indekslere ekler (write-through)."""
        self.ensure_loaded()
        self._items.append(item)
        self._index_item(item)
        self._stats.adds += 1
        log.debug("[%s] cache'e yeni kayıt eklendi: %s", self.name, item)

    def all(self) -> List[dict]:
        self.ensure_loaded()
        return list(self._items)

    def stats(self) -> _Stats:
        return self._stats


class BeyondTrustCache:
    """
    Tüm varlık cache'lerini bir arada tutan yönetici.

    Kullanım:
        cache = BeyondTrustCache()
        cache.register("UserGroup", loader=..., key_funcs={"name": lambda x: x["Name"]})
        grp = cache.get("UserGroup", "name", "sbmuser1")
    """

    def __init__(self):
        self._caches: Dict[str, EntityCache] = {}

    def register(self, name: str, loader: LoaderFunc, key_funcs: Dict[str, KeyFunc]) -> EntityCache:
        ec = EntityCache(name=name, loader=loader, key_funcs=key_funcs)
        self._caches[name] = ec
        log.debug("Cache kaydı tanımlandı: %s", name)
        return ec

    def entity(self, name: str) -> EntityCache:
        if name not in self._caches:
            raise KeyError(f"Tanımsız cache: {name}")
        return self._caches[name]

    def get(self, name: str, index_name: str, value) -> Optional[dict]:
        return self.entity(name).get(index_name, value)

    def add(self, name: str, item: dict) -> None:
        self.entity(name).add(item)

    def preload_all(self) -> None:
        """Tüm kayıtlı cache'leri baştan yükler (opsiyonel ön ısıtma)."""
        for ec in self._caches.values():
            ec.ensure_loaded()

    def log_stats(self) -> None:
        for name, ec in self._caches.items():
            s = ec.stats()
            log.info(
                "[cache:%s] kayıt=%d, hit=%d, miss=%d, eklenen=%d",
                name, len(ec.all()), s.hits, s.misses, s.adds,
            )
