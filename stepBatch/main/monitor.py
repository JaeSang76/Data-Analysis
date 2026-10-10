from __future__ import annotations

import os
from datetime import datetime, timezone

from . import db


def current_snapshot():
    rows = db.list_batches()
    result = []
    for row in rows:
        item = dict(row)
        item["process_alive"] = None
        if row["status"] == "RUNNING":
            # Most recent execution is enough for an operational snapshot.
            with db.connection() as conn:
                execution = conn.execute(
                    """SELECT pid, started_at, status, log_file FROM batch_execution
                       WHERE batch_id=%s ORDER BY execution_id DESC LIMIT 1""",
                    (row["batch_id"],),
                ).fetchone()
            if execution:
                item["pid"] = execution["pid"]
                item["execution_started_at"] = execution["started_at"]
                item["log_file"] = execution["log_file"]
                if execution["pid"]:
                    try:
                        os.kill(execution["pid"], 0)
                        item["process_alive"] = True
                    except OSError:
                        item["process_alive"] = False
        result.append(item)
    return result


def print_snapshot() -> None:
    rows = current_snapshot()
    print("\nBATCH | STATUS | ENABLED | PID | PROCESS | LAST RESULT | LAST START")
    print("-" * 110)
    for row in rows:
        print(
            f"{row['batch_id']} | {row['status']} | {row['enabled']} | "
            f"{row.get('pid', '-')} | {row.get('process_alive', '-')} | "
            f"{row['last_result'] or '-'} | {row['last_start_at'] or '-'}"
        )
