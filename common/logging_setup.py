# -*- coding: utf-8 -*-
"""
Merkezi loglama kurulumu.

Hedef: kullanıcı, "nerede ne oldu"yu çok net görsün.
  * Konsol  -> renkli, sade, akışı takip etmek için (INFO ve üstü).
  * Dosya   -> ayrıntılı, zaman damgalı, modül + satır numaralı (DEBUG ve üstü).

Hiçbir 3. parti bağımlılık (colorama vb.) gerektirmez; ANSI renkleri elle
yönetilir ve Windows'ta sanal terminal modu açılır.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# ANSI renkleri
# ---------------------------------------------------------------------------
class _Ansi:
    RESET = "\033[0m"
    GREY = "\033[90m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    BOLD_RED = "\033[1;31m"


_LEVEL_COLORS = {
    logging.DEBUG: _Ansi.GREY,
    logging.INFO: _Ansi.GREEN,
    logging.WARNING: _Ansi.YELLOW,
    logging.ERROR: _Ansi.RED,
    logging.CRITICAL: _Ansi.BOLD_RED,
}


def _enable_windows_ansi() -> None:
    """Windows konsolunda ANSI renk desteğini açmayı dener (sessizce geçer)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # STD_OUTPUT_HANDLE = -11 ; ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        # Renk açılamazsa sorun değil; düz metin yine yazılır.
        pass


class _ColorConsoleFormatter(logging.Formatter):
    """Konsol için renkli, sade formatlayıcı."""

    def __init__(self, use_color: bool):
        super().__init__()
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        level = record.levelname.ljust(7)
        msg = record.getMessage()
        line = f"{ts} | {level} | {msg}"
        if self.use_color:
            color = _LEVEL_COLORS.get(record.levelno, "")
            line = f"{color}{line}{_Ansi.RESET}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def setup_logging(
    log_dir: Path,
    console_level: str = "INFO",
    file_level: str = "DEBUG",
    use_color: bool = True,
) -> Path:
    """
    Kök logger'ı yapılandırır ve log dosyasının yolunu döndürür.

    Her çalıştırma için zaman damgalı yeni bir log dosyası oluşturulur, böylece
    geçmiş çalışmalar üzerine yazılmaz.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"sbm_migration_{timestamp}.log"

    _enable_windows_ansi()

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # Önceki handler'ları temizle (tekrar çağrılırsa çift log olmasın).
    for handler in list(root.handlers):
        root.removeHandler(handler)

    # --- Konsol handler ---
    console = logging.StreamHandler(stream=sys.stdout)
    console.setLevel(getattr(logging, console_level.upper(), logging.INFO))
    console.setFormatter(_ColorConsoleFormatter(use_color=use_color))
    root.addHandler(console)

    # --- Dosya handler (ayrıntılı) ---
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(getattr(logging, file_level.upper(), logging.DEBUG))
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)-18s | "
            "%(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(file_handler)

    return log_file


def get_logger(name: str) -> logging.Logger:
    """Modüller için kısayol."""
    return logging.getLogger(name)
