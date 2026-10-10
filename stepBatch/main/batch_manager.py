from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import db
from .config import ALLOWED_SOURCES, CRON_FILES_DIR
from .schedule import build_cron_expression
from .scheduler import install_batch_cron, remove_batch_cron

BATCH_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def validate_script(source_type: str, script_name: str) -> Path:
    if source_type not in ALLOWED_SOURCES:
        raise ValueError(f"source_type은 {sorted(ALLOWED_SOURCES)} 중 하나여야 합니다.")
    if Path(script_name).name != script_name or not script_name.endswith(".py"):
        raise ValueError("script_name은 하위경로를 포함하지 않는 .py 파일명이어야 합니다.")
    path = CRON_FILES_DIR / source_type / script_name
    if not path.is_file():
        raise FileNotFoundError(f"실행파일이 없습니다: {path}")
    return path


def validate_batch_id(batch_id: str) -> None:
    if not BATCH_ID_RE.fullmatch(batch_id):
        raise ValueError("batch_id는 영문/숫자/_/-만 사용하고 1~100자로 입력하세요.")


def prepare_data(
    *, batch_id: str, batch_name: str, source_type: str, script_name: str,
    data_year: int, schedule_type: str, start_time: str, end_time: str,
    interval_minutes: int, weekday: int | None, month_day: int | None,
    timeout_seconds: int, retry_count: int, cron_expression: str | None = None,
) -> dict[str, Any]:
    validate_batch_id(batch_id)
    validate_script(source_type, script_name)
    if not 1900 <= data_year <= 2100:
        raise ValueError("data_year는 1900~2100 범위로 입력하세요.")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds는 1 이상이어야 합니다.")
    if retry_count < 0:
        raise ValueError("retry_count는 0 이상이어야 합니다.")

    if schedule_type == "CUSTOM":
        if not cron_expression:
            raise ValueError("CUSTOM은 cron_expression이 필요합니다.")
        expression = cron_expression.strip()
        fields = expression.split()
        if len(fields) != 5:
            raise ValueError("CUSTOM cron은 5개 필드(분 시 일 월 요일)여야 합니다.")
    else:
        expression = build_cron_expression(
            schedule_type, start_time, end_time, interval_minutes, weekday, month_day
        )

    return {
        "batch_id": batch_id,
        "batch_name": batch_name,
        "source_type": source_type,
        "script_name": script_name,
        "data_year": data_year,
        "schedule_type": schedule_type,
        "cron_expression": expression,
        "start_time": start_time,
        "end_time": end_time,
        "interval_minutes": interval_minutes,
        "weekday": weekday,
        "month_day": month_day,
        "timeout_seconds": timeout_seconds,
        "retry_count": retry_count,
    }


def create(data: dict[str, Any]) -> None:
    if db.get_batch(data["batch_id"]):
        raise ValueError("이미 존재하는 batch_id입니다.")
    db.insert_batch(data)
    try:
        install_batch_cron(data["batch_id"], data["cron_expression"])
        db.set_status(data["batch_id"], "READY", True)
    except Exception:
        db.delete_batch(data["batch_id"])
        raise


def update(batch_id: str, data: dict[str, Any]) -> None:
    old = db.get_batch(batch_id)
    if not old:
        raise KeyError(batch_id)
    remove_batch_cron(batch_id)
    try:
        db.update_batch(batch_id, data)
        if old["status"] != "STOPPED":
            install_batch_cron(batch_id, data["cron_expression"])
            db.set_status(batch_id, "READY", True)
    except Exception:
        # Best effort restoration of the previous schedule.
        install_batch_cron(batch_id, old["cron_expression"])
        raise


def delete(batch_id: str) -> None:
    old = db.get_batch(batch_id)
    if not old:
        raise KeyError(batch_id)
    if old["status"] == "RUNNING":
        raise RuntimeError("RUNNING 상태에서는 삭제할 수 없습니다. 먼저 중지하세요.")
    remove_batch_cron(batch_id)
    db.delete_batch(batch_id)


def stop(batch_id: str) -> None:
    if not db.get_batch(batch_id):
        raise KeyError(batch_id)
    remove_batch_cron(batch_id)
    db.set_status(batch_id, "STOPPED", False)


def resume(batch_id: str) -> None:
    row = db.get_batch(batch_id)
    if not row:
        raise KeyError(batch_id)
    install_batch_cron(batch_id, row["cron_expression"])
    db.set_status(batch_id, "READY", True)
