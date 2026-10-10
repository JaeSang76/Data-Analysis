from __future__ import annotations

import argparse
import sys
from datetime import datetime

from . import batch_manager, db
from .config import ALLOWED_SOURCES, ensure_directories
from .scheduler import managed_crons
from .monitor import print_snapshot


def _input_int(prompt: str, min_value: int | None = None, max_value: int | None = None) -> int:
    while True:
        try:
            value = int(input(prompt).strip())
            if min_value is not None and value < min_value:
                raise ValueError
            if max_value is not None and value > max_value:
                raise ValueError
            return value
        except ValueError:
            print("올바른 숫자를 입력하세요.")


def _input_time(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        try:
            datetime.strptime(value, "%H:%M")
            return value
        except ValueError:
            print("HH:MM 형식으로 입력하세요. 예: 02:30")


def _input_common() -> dict:
    batch_id = input("배치 ID: ").strip()
    batch_name = input("배치명: ").strip()
    print("데이터 수집 방식: API / DB / file / webScraping")
    source_type = input("데이터 수집 방식: ").strip()
    script_name = input("실행 Python 파일명: ").strip()
    data_year = _input_int("데이터 수집 연도: ", 1900, 2100)

    print("스케줄: DAILY / WEEKDAY / WEEKLY / MONTHLY / CUSTOM")
    schedule_type = input("실행 주기: ").strip().upper()
    start_time = _input_time("실행 시작시간(HH:MM): ")
    end_time = _input_time("실행 종료시간(HH:MM): ")
    interval_minutes = _input_int("반복 간격(분, 1~1440): ", 1, 1440)

    weekday = None
    month_day = None
    if schedule_type == "WEEKLY":
        weekday = _input_int("요일(0=월요일~6=일요일): ", 0, 6)
    elif schedule_type == "MONTHLY":
        month_day = _input_int("월의 일자(1~31): ", 1, 31)

    cron_expression = None
    if schedule_type == "CUSTOM":
        cron_expression = input("Cron 표현식(분 시 일 월 요일): ").strip()

    timeout_seconds = _input_int("최대 실행시간(초): ", 1)
    retry_count = _input_int("재시도 횟수: ", 0)
    return batch_manager.prepare_data(
        batch_id=batch_id,
        batch_name=batch_name,
        source_type=source_type,
        script_name=script_name,
        data_year=data_year,
        schedule_type=schedule_type,
        start_time=start_time,
        end_time=end_time,
        interval_minutes=interval_minutes,
        weekday=weekday,
        month_day=month_day,
        timeout_seconds=timeout_seconds,
        retry_count=retry_count,
        cron_expression=cron_expression,
    )


def print_batches() -> None:
    rows = db.list_batches()
    if not rows:
        print("등록된 배치가 없습니다.")
        return
    print("\nID | SOURCE | YEAR | SCHEDULE | STATUS | LAST RESULT | LAST START")
    print("-" * 110)
    for row in rows:
        print(
            f"{row['batch_id']} | {row['source_type']} | {row['data_year']} | "
            f"{row['cron_expression']} | {row['status']} | {row['last_result'] or '-'} | {row['last_start_at'] or '-'}"
        )


def register() -> None:
    data = _input_common()
    print("\n생성될 Cron:", data["cron_expression"])
    if input("등록하시겠습니까? [Y/N]: ").strip().upper() == "Y":
        batch_manager.create(data)
        print("등록 완료: READY")


def update() -> None:
    batch_id = input("수정할 batch ID: ").strip()
    data = _input_common()
    data["batch_id"] = batch_id
    print("\n변경될 Cron:", data["cron_expression"])
    if input("수정하시겠습니까? [Y/N]: ").strip().upper() == "Y":
        batch_manager.update(batch_id, data)
        print("수정 완료")


def menu() -> None:
    ensure_directories()
    db.initialize_database()
    while True:
        print("""
====================================================
 STEP Batch Management System
====================================================
1. 배치 등록
2. 배치 수정
3. 배치 삭제
4. 배치 중지
5. 배치 재개
6. 배치 상태 조회
7. 실시간 모니터링
8. 실행 이력 조회
9. 관리 Cron 조회
0. 종료
====================================================
""")
        choice = input("선택: ").strip()
        try:
            if choice == "1":
                register()
            elif choice == "2":
                update()
            elif choice == "3":
                batch_id = input("삭제할 batch ID: ").strip()
                if input("정말 삭제하시겠습니까? [Y/N]: ").strip().upper() == "Y":
                    batch_manager.delete(batch_id)
                    print("삭제 완료")
            elif choice == "4":
                batch_id = input("중지할 batch ID: ").strip()
                batch_manager.stop(batch_id)
                print("중지 완료: STOPPED")
            elif choice == "5":
                batch_id = input("재개할 batch ID: ").strip()
                batch_manager.resume(batch_id)
                print("재개 완료: READY")
            elif choice == "6":
                print_batches()
            elif choice == "7":
                print_snapshot()
            elif choice == "8":
                batch_id = input("batch ID (전체는 Enter): ").strip() or None
                for row in db.list_executions(batch_id):
                    print(f"#{row['execution_id']} {row['batch_id']} {row['status']} "
                          f"started={row['started_at']} ended={row['ended_at']} "
                          f"exit={row['exit_code']} log={row['log_file']}")
            elif choice == "9":
                for line in managed_crons():
                    print(line)
            elif choice == "0":
                break
            else:
                print("올바른 메뉴를 선택하세요.")
        except Exception as exc:
            print(f"[ERROR] {exc}")


def cli() -> int:
    parser = argparse.ArgumentParser(description="STEP Batch Management System")
    parser.add_argument("--init-db", action="store_true", help="Initialize database schema")
    args = parser.parse_args()
    ensure_directories()
    if args.init_db:
        db.initialize_database()
        print("Database schema initialized.")
        return 0
    menu()
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
