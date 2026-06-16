# -*- coding: utf-8 -*-
"""
Part 2 için dummy envanter üretici.

3 kullanıcı / 3 safe, her biri için 3 sunucu (Linux/windows karışık) üretir
ve data/PamEnvanter.xlsx + data/OsEnvanter.xlsx dosyalarını yazar.
Domain: quasys.com.tr

Çalıştırma:
    python -m scripts.generate_dummy_inventory
"""

from __future__ import annotations

import openpyxl

from common.logging_setup import get_logger, setup_logging
from config import settings

log = get_logger("dummy_gen")

DOMAIN = settings.DEFAULT_DOMAIN  # quasys.com.tr

# (userName, safeName, [(hostname, ip, os), ...])  — remoteMachines karışık (ip/hostname)
USERS = [
    ("srvsbmuser1", "sbmuser1", [
        ("sbmsrv11", "10.20.30.11", "Linux"),
        ("sbmsrv12", "10.20.30.12", "windows"),
        ("sbmsrv13", "10.20.30.13", "Linux"),
    ]),
    ("srvsbmuser2", "sbmuser2", [
        ("sbmsrv21", "10.20.30.21", "windows"),
        ("sbmsrv22", "10.20.30.22", "Linux"),
        ("sbmsrv23", "10.20.30.23", "windows"),
    ]),
    ("srvsbmuser3", "sbmuser3", [
        ("sbmsrv31", "10.20.30.31", "Linux"),
        ("sbmsrv32", "10.20.30.32", "windows"),
        ("sbmsrv33", "10.20.30.33", "Linux"),
    ]),
]


def _write_os_envanter() -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Hostname", "IP Address", "OS", "Domain"])
    for _user, _safe, servers in USERS:
        for hostname, ip, os_val in servers:
            ws.append([hostname, ip, os_val, DOMAIN])
    wb.save(settings.OS_ENVANTER_FILE)
    log.info("OsEnvanter yazıldı: %s", settings.OS_ENVANTER_FILE)


def _write_pam_envanter() -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["userName", "safeName", "remoteMachines"])
    for user, safe, servers in USERS:
        # remoteMachines'i ip ve hostname karışık üret (ilk ip, ikinci hostname...)
        tokens = []
        for i, (hostname, ip, _os) in enumerate(servers):
            tokens.append(ip if i % 2 == 0 else hostname)
        ws.append([user, safe, settings.REMOTE_MACHINES_SEPARATOR.join(tokens)])
    wb.save(settings.PAM_ENVANTER_FILE)
    log.info("PamEnvanter yazıldı: %s", settings.PAM_ENVANTER_FILE)


def main() -> None:
    setup_logging(settings.LOG_DIR, settings.CONSOLE_LOG_LEVEL,
                  settings.FILE_LOG_LEVEL, settings.USE_COLOR)
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Dummy envanter üretiliyor (domain=%s, %d kullanıcı)...", DOMAIN, len(USERS))
    _write_os_envanter()
    _write_pam_envanter()
    log.info("Dummy envanter hazır. ✔")


if __name__ == "__main__":
    main()
