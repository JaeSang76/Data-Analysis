from __future__ import annotations

from datetime import datetime, time


def _parse_hhmm(value: str) -> time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise ValueError("시간은 HH:MM 형식이어야 합니다. 예: 02:30") from exc


def build_cron_expressions(
    schedule_type: str,
    start_time: str,
    end_time: str,
    interval_minutes: int,
    weekday: int | None = None,
    month_day: int | None = None,
) -> list[str]:
    start = _parse_hhmm(start_time)
    end = _parse_hhmm(end_time)
    if start > end:
        raise ValueError("이번 구현에서는 시작시간이 종료시간보다 늦을 수 없습니다.")
    if not (1 <= interval_minutes <= 1440):
        raise ValueError("interval_minutes는 1~1440 범위여야 합니다.")

    if schedule_type == "CUSTOM":
        raise ValueError("CUSTOM은 cron_expression을 직접 입력해야 합니다.")

    points: list[tuple[int, int]] = []
    cursor = start.hour * 60 + start.minute
    end_minute = end.hour * 60 + end.minute
    while cursor <= end_minute:
        points.append((cursor // 60, cursor % 60))
        cursor += interval_minutes

    # Group only by hour. This avoids creating invalid times such as 04:30
    # when the requested window ends at 04:00.
    by_hour: dict[int, list[int]] = {}
    for hour, minute in points:
        by_hour.setdefault(hour, []).append(minute)

    suffix = "* * *"
    if schedule_type == "WEEKDAY":
        suffix = "* * 1-5"
    elif schedule_type == "WEEKLY":
        if weekday is None or not 0 <= weekday <= 6:
            raise ValueError("WEEKLY는 weekday(0=월요일~6=일요일)가 필요합니다.")
        suffix = f"* * {(weekday + 1) % 7}"
    elif schedule_type == "MONTHLY":
        if month_day is None or not 1 <= month_day <= 31:
            raise ValueError("MONTHLY는 month_day(1~31)가 필요합니다.")
        suffix = f"{month_day} * *"
    elif schedule_type != "DAILY":
        raise ValueError(f"지원하지 않는 schedule_type: {schedule_type}")

    return [f"{','.join(map(str, minutes))} {hour} {suffix}" for hour, minutes in sorted(by_hour.items())]


def build_cron_expression(*args, **kwargs) -> str:
    expressions = build_cron_expressions(*args, **kwargs)
    return "\n".join(expressions)
