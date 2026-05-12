"""
logging_config.py  — Centralised logging for LIS Ask
  • Console  → step-by-step pipeline trace (INFO+)
  • File     → full debug dump to lis_ask_debug.log
  • Suppresses noisy 3rd-party libs (httpx, groq, urllib3)
"""
import logging
import sys
import os
from datetime import datetime

# ─── public API ──────────────────────────────────────────────────────────────

def setup_logging(level: int = logging.DEBUG, log_file: str = "lis_ask_debug.log") -> logging.Logger:
    """
    Call once at app startup.
    Returns the root logger (already attached to every module via getLogger(__name__)).
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()           # avoid duplicate handlers on hot-reload

    # ── console ──────────────────────────────────────────────────────────────
    con = logging.StreamHandler(sys.stdout)
    con.setLevel(level)
    con.setFormatter(_ConsoleFormatter())
    root.addHandler(con)

    # ── file  ─────────────────────────────────────────────────────────────────
    try:
        fh = logging.FileHandler(log_file, encoding="utf-8", mode="a")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(_FileFormatter())
        root.addHandler(fh)
    except OSError as e:
        root.warning(f"Could not open log file {log_file}: {e}")

    # ── silence chatty third-party libs ──────────────────────────────────────
    for noisy in ("httpx", "httpcore", "urllib3", "groq", "openai",
                  "watchdog", "streamlit", "tornado", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root.info("")
    root.info("=" * 64)
    root.info("  LIS Ask — logging started")
    root.info(f"  Console level : {logging.getLevelName(level)}")
    root.info(f"  Log file      : {os.path.abspath(log_file)}")
    root.info("=" * 64)
    return root


# ─── formatters ──────────────────────────────────────────────────────────────

_LEVEL_ICONS = {
    "DEBUG"   : "   DBG",
    "INFO"    : "   ---",
    "WARNING" : "   WRN",
    "ERROR"   : "!! ERR",
    "CRITICAL": "!! CRT",
}

class _ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts     = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        icon   = _LEVEL_ICONS.get(record.levelname, "   ---")
        msg    = record.getMessage()

        # exception traceback if present
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)

        return f"{ts}  {icon}  {msg}"


class _FileFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts  = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{ts}  {record.levelname:<8}  {record.name:<30}  {msg}"
