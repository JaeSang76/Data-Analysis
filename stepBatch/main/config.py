from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path("/opt/stepBatch")
# Development/test fallback: if the package is copied elsewhere, use its parent.
if not BASE_DIR.exists():
    BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

MAIN_DIR = BASE_DIR / "main"
CRON_FILES_DIR = BASE_DIR / "cronFiles"
LOG_DIR = BASE_DIR / "logs"
EXECUTION_LOG_DIR = LOG_DIR / "execution"
RUNTIME_DIR = BASE_DIR / "runtime"
LOCK_DIR = RUNTIME_DIR / "locks"
PID_DIR = RUNTIME_DIR / "pid"
STATUS_DIR = RUNTIME_DIR / "status"
CONFIG_DIR = BASE_DIR / "config"

TIMEZONE = os.getenv("TIMEZONE", "Asia/Seoul")
DATABASE_URL = os.getenv("DATABASE_URL", "")
PYTHON_BIN = os.getenv("PYTHON_BIN", str(BASE_DIR / "venv/bin/python"))
CRONTAB_BIN = os.getenv("CRONTAB_BIN", "/usr/bin/crontab")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

CRON_BEGIN = "# STEP_BATCH_BEGIN"
CRON_END = "# STEP_BATCH_END"

ALLOWED_SOURCES = {"API", "DB", "file", "webScraping"}
ALLOWED_STATUS = {"REGISTERED", "READY", "RUNNING", "STOPPED", "FAILED"}
ALLOWED_RESULTS = {"SUCCESS", "FAILED", "TIMEOUT", "CANCELLED", "SKIPPED"}


def ensure_directories() -> None:
    for path in (
        MAIN_DIR,
        CRON_FILES_DIR,
        LOG_DIR,
        EXECUTION_LOG_DIR,
        RUNTIME_DIR,
        LOCK_DIR,
        PID_DIR,
        STATUS_DIR,
        CONFIG_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
