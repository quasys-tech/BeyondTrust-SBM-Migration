# -*- coding: utf-8 -*-
"""
SBM Migration - Part 1  (Hazırlık / Korelasyon)
================================================

Akış:
  1. PamEnvanter.xlsx ve OsEnvanter.xlsx okunur.
  2. OS envanteri için arama indeksi (IP + hostname) kurulur.
  3. PamEnvanter satırları OsEnvanter ile korele edilir.
  4. Sonuç Working.xlsx olarak yazılır ('Working' + 'Ignored Rows' sayfaları).
  5. Net bir özet rapor (konsol + log dosyası) basılır.

Çalıştırma:
    python main.py
"""

from __future__ import annotations

import sys
import time

from config import settings
from correlation.correlator import Correlator, CorrelationResult
from correlation.excel_reader import read_os_envanter, read_pam_envanter
from correlation.excel_writer import write_working_file
from common.logging_setup import get_logger, setup_logging

log = get_logger("main")


def _print_summary(result: CorrelationResult, elapsed: float, log_file) -> None:
    """Çalışmanın net özetini basar."""
    lines = [
        "",
        "==================== ÖZET RAPOR ====================",
        f"  PamEnvanter satırı (toplam)      : {result.pam_rows_total}",
        f"  remoteMachines'siz satır          : {result.pam_rows_without_remote}",
        f"  İşlenen remoteMachines değeri     : {result.remote_items_total}",
        "  --------------------------------------------------",
        f"  WORKING (başarılı eşleşme)        : {result.matched_items}",
        f"  IGNORED - OsEnvanter'da yok       : {result.ignored_no_match}",
        f"  IGNORED - OS bilgisi boş          : {result.ignored_no_os}",
        f"  IGNORED - duplicate/belirsiz      : {result.ignored_duplicate}",
        f"  IGNORED (toplam)                  : {len(result.ignored_rows)}",
        "  --------------------------------------------------",
        f"  DEFAULT_DOMAIN kullanıldı         : {result.default_domain_used} kez",
        f"  Çıktı dosyası                     : {settings.WORKING_FILE}",
        f"  Log dosyası                       : {log_file}",
        f"  Süre                              : {elapsed:.2f} sn",
        "====================================================",
        "",
    ]
    for line in lines:
        log.info(line)


def run() -> int:
    log_file = setup_logging(
        log_dir=settings.LOG_DIR,
        console_level=settings.CONSOLE_LOG_LEVEL,
        file_level=settings.FILE_LOG_LEVEL,
        use_color=settings.USE_COLOR,
    )
    start = time.perf_counter()

    log.info("####################################################")
    log.info("#  SBM Migration - Part 1 (Korelasyon) başlıyor    #")
    log.info("####################################################")

    try:
        # 1) Girdileri oku
        os_records = read_os_envanter(settings.OS_ENVANTER_FILE, settings.OS_SHEET_NAME)
        pam_rows = read_pam_envanter(settings.PAM_ENVANTER_FILE, settings.PAM_SHEET_NAME)

        # 2) İndeks kur
        from correlation.os_inventory import OsInventory

        inventory = OsInventory(os_records)

        # 3) Korele et
        correlator = Correlator(inventory, default_domain=settings.DEFAULT_DOMAIN)
        result = correlator.correlate(pam_rows)

        # 4) Çıktı yaz
        write_working_file(
            output_file=settings.WORKING_FILE,
            working_rows=result.working_rows,
            ignored_rows=result.ignored_rows,
            working_sheet_name=settings.WORKING_SHEET_NAME,
            ignored_sheet_name=settings.IGNORED_SHEET_NAME,
        )

        # 5) Özet
        elapsed = time.perf_counter() - start
        _print_summary(result, elapsed, log_file)

        log.info("Part 1 başarıyla tamamlandı. ✔")
        return 0

    except FileNotFoundError as exc:
        log.error("Dosya bulunamadı: %s", exc)
        return 2
    except ValueError as exc:
        log.error("Veri/şema hatası: %s", exc)
        return 3
    except Exception:  # noqa: BLE001 - en üst seviyede her şeyi yakala ve logla
        log.exception("Beklenmeyen hata oluştu, çalışma durduruldu.")
        return 1


def run_pipeline() -> int:
    """
    Tüm akışı sırayla çalıştırır:
        1) Part 1 — Korelasyon (Working.xlsx üretir; migrate.py bunu okur)
        2) migrate.py — Part 2 + 3 + 4 (her satır 'type' kolonuna göre AD veya
           LOCAL sürecine yönlendirilir; tek ortak working excel'i kullanılır)

    Part 1 başarısızsa zincir durur (migrate.py'nin girdisi üretilemez).
    """
    # 1) Part 1 — Korelasyon
    rc_corr = run()
    if rc_corr != 0:
        log.error("Part 1 (korelasyon) başarısız (kod=%s); zincir durduruldu.", rc_corr)
        return rc_corr

    # 2) migrate.py — Part 2 + 3 + 4 (AD/LOCAL routing 'type' kolonuna göre)
    log.info("")
    log.info(">>> Zincir: migrate.py (Part 2+3+4, AD/LOCAL routing) başlatılıyor...")
    import migrate

    rc_migrate = migrate.run()
    if rc_migrate == 0:
        log.info("ZİNCİR TAMAMLANDI: korelasyon + migrate (AD+LOCAL) ✔")
    else:
        log.warning("ZİNCİR BİTTİ ama migrate hata kodu döndü: %s", rc_migrate)
    return rc_migrate


if __name__ == "__main__":
    sys.exit(run_pipeline())
