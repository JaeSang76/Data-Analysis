from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from .config import DATABASE_URL

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS batch_job (
    batch_id            VARCHAR(100) PRIMARY KEY,
    batch_name          VARCHAR(200) NOT NULL,
    source_type         VARCHAR(30) NOT NULL,
    script_name         VARCHAR(255) NOT NULL,
    data_year           INTEGER NOT NULL,
    schedule_type       VARCHAR(20) NOT NULL,
    cron_expression     TEXT NOT NULL,
    start_time          TIME NOT NULL,
    end_time            TIME NOT NULL,
    interval_minutes    INTEGER NOT NULL DEFAULT 1440,
    weekday             INTEGER,
    month_day           INTEGER,
    timeout_seconds     INTEGER NOT NULL DEFAULT 3600,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    status              VARCHAR(20) NOT NULL DEFAULT 'REGISTERED',
    last_start_at       TIMESTAMPTZ,
    last_end_at         TIMESTAMPTZ,
    last_result         VARCHAR(20),
    last_exit_code      INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_batch_source CHECK (source_type IN ('API','DB','file','webScraping')),
    CONSTRAINT ck_batch_status CHECK (status IN ('REGISTERED','READY','RUNNING','STOPPED','FAILED')),
    CONSTRAINT ck_batch_result CHECK (last_result IS NULL OR last_result IN ('SUCCESS','FAILED','TIMEOUT','CANCELLED','SKIPPED')),
    CONSTRAINT ck_batch_interval CHECK (interval_minutes > 0 AND interval_minutes <= 1440),
    CONSTRAINT ck_batch_timeout CHECK (timeout_seconds > 0),
    CONSTRAINT ck_batch_retry CHECK (retry_count >= 0),
    CONSTRAINT ck_batch_weekday CHECK (weekday IS NULL OR weekday BETWEEN 0 AND 6),
    CONSTRAINT ck_batch_month_day CHECK (month_day IS NULL OR month_day BETWEEN 1 AND 31)
);

CREATE TABLE IF NOT EXISTS batch_execution (
    execution_id       BIGSERIAL PRIMARY KEY,
    batch_id           VARCHAR(100) NOT NULL REFERENCES batch_job(batch_id) ON DELETE CASCADE,
    scheduled_at       TIMESTAMPTZ,
    started_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at           TIMESTAMPTZ,
    status             VARCHAR(20) NOT NULL,
    exit_code          INTEGER,
    pid                INTEGER,
    attempt            INTEGER NOT NULL DEFAULT 1,
    log_file           TEXT,
    error_message      TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_execution_status CHECK (status IN ('RUNNING','SUCCESS','FAILED','TIMEOUT','CANCELLED','SKIPPED'))
);

CREATE INDEX IF NOT EXISTS ix_batch_execution_batch_started
    ON batch_execution(batch_id, started_at DESC);
"""


def _require_db_url() -> None:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured in /opt/stepBatch/.env")


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    _require_db_url()
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def initialize_database() -> None:
    with connection() as conn:
        conn.execute(SCHEMA_SQL)
        conn.commit()


def get_batch(batch_id: str):
    with connection() as conn:
        return conn.execute(
            "SELECT * FROM batch_job WHERE batch_id = %s", (batch_id,)
        ).fetchone()


def list_batches():
    with connection() as conn:
        return conn.execute(
            "SELECT * FROM batch_job ORDER BY batch_id"
        ).fetchall()


def insert_batch(data: dict) -> None:
    sql = """
    INSERT INTO batch_job (
        batch_id, batch_name, source_type, script_name, data_year,
        schedule_type, cron_expression, start_time, end_time,
        interval_minutes, weekday, month_day, timeout_seconds,
        retry_count, enabled, status
    ) VALUES (
        %(batch_id)s, %(batch_name)s, %(source_type)s, %(script_name)s, %(data_year)s,
        %(schedule_type)s, %(cron_expression)s, %(start_time)s, %(end_time)s,
        %(interval_minutes)s, %(weekday)s, %(month_day)s, %(timeout_seconds)s,
        %(retry_count)s, TRUE, 'REGISTERED'
    )
    """
    with connection() as conn:
        conn.execute(sql, data)
        conn.commit()


def update_batch(batch_id: str, data: dict) -> None:
    data = {**data, "batch_id": batch_id}
    sql = """
    UPDATE batch_job SET
        batch_name=%(batch_name)s,
        source_type=%(source_type)s,
        script_name=%(script_name)s,
        data_year=%(data_year)s,
        schedule_type=%(schedule_type)s,
        cron_expression=%(cron_expression)s,
        start_time=%(start_time)s,
        end_time=%(end_time)s,
        interval_minutes=%(interval_minutes)s,
        weekday=%(weekday)s,
        month_day=%(month_day)s,
        timeout_seconds=%(timeout_seconds)s,
        retry_count=%(retry_count)s,
        updated_at=CURRENT_TIMESTAMP
    WHERE batch_id=%(batch_id)s
    """
    with connection() as conn:
        cur = conn.execute(sql, data)
        if cur.rowcount != 1:
            raise KeyError(f"Unknown batch_id: {batch_id}")
        conn.commit()


def set_status(batch_id: str, status: str, enabled: bool | None = None) -> None:
    with connection() as conn:
        if enabled is None:
            cur = conn.execute(
                "UPDATE batch_job SET status=%s, updated_at=CURRENT_TIMESTAMP WHERE batch_id=%s",
                (status, batch_id),
            )
        else:
            cur = conn.execute(
                "UPDATE batch_job SET status=%s, enabled=%s, updated_at=CURRENT_TIMESTAMP WHERE batch_id=%s",
                (status, enabled, batch_id),
            )
        if cur.rowcount != 1:
            raise KeyError(f"Unknown batch_id: {batch_id}")
        conn.commit()


def delete_batch(batch_id: str) -> None:
    with connection() as conn:
        cur = conn.execute("DELETE FROM batch_job WHERE batch_id=%s", (batch_id,))
        if cur.rowcount != 1:
            raise KeyError(f"Unknown batch_id: {batch_id}")
        conn.commit()


def create_execution(batch_id: str, scheduled_at: datetime | None, pid: int | None, log_file: str, attempt: int = 1) -> int:
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO batch_execution(batch_id, scheduled_at, status, pid, log_file, attempt)
            VALUES (%s, %s, 'RUNNING', %s, %s, %s)
            RETURNING execution_id
            """,
            (batch_id, scheduled_at, pid, log_file, attempt),
        ).fetchone()
        conn.commit()
        return int(row["execution_id"])


def finish_execution(execution_id: int, status: str, exit_code: int | None, error_message: str | None = None) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE batch_execution
               SET ended_at=CURRENT_TIMESTAMP, status=%s, exit_code=%s, error_message=%s
             WHERE execution_id=%s
            """,
            (status, exit_code, error_message, execution_id),
        )
        conn.commit()


def mark_started(batch_id: str) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE batch_job SET status='RUNNING', last_start_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE batch_id=%s",
            (batch_id,),
        )
        conn.commit()


def mark_finished(batch_id: str, result: str, exit_code: int | None) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE batch_job
               SET status=(CASE WHEN status='STOPPED' THEN 'STOPPED'
                                WHEN %s='SUCCESS' THEN 'READY'
                                ELSE 'FAILED' END),
                   enabled=(CASE WHEN status='STOPPED' THEN FALSE ELSE enabled END),
                   last_end_at=CURRENT_TIMESTAMP, last_result=%s,
                   last_exit_code=%s, updated_at=CURRENT_TIMESTAMP
             WHERE batch_id=%s
            """,
            (result, result, exit_code, batch_id),
        )
        conn.commit()


def list_executions(batch_id: str | None = None, limit: int = 20):
    with connection() as conn:
        if batch_id:
            return conn.execute(
                "SELECT * FROM batch_execution WHERE batch_id=%s ORDER BY execution_id DESC LIMIT %s",
                (batch_id, limit),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM batch_execution ORDER BY execution_id DESC LIMIT %s",
            (limit,),
        ).fetchall()


def try_advisory_lock(conn: psycopg.Connection, batch_id: str) -> bool:
    # PostgreSQL advisory locks are application-defined locks and are released
    # automatically when the database session ends.
    row = conn.execute(
        "SELECT pg_try_advisory_lock(hashtextextended(%s, 7331)) AS locked",
        (batch_id,),
    ).fetchone()
    return bool(row["locked"])


def release_advisory_lock(conn: psycopg.Connection, batch_id: str) -> None:
    conn.execute(
        "SELECT pg_advisory_unlock(hashtextextended(%s, 7331))",
        (batch_id,),
    )
