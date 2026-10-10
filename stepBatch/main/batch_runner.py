from __future__ import annotations

import argparse
import os
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import db
from .config import BASE_DIR, CRON_FILES_DIR, EXECUTION_LOG_DIR, PYTHON_BIN, ensure_directories
from .logger import get_logger

logger = get_logger("stepbatch.runner")


def _kill_process_tree(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run(batch_id: str) -> int:
    ensure_directories()
    batch = db.get_batch(batch_id)
    if not batch:
        logger.error("Unknown batch_id=%s", batch_id)
        return 2
    if not batch["enabled"] or batch["status"] == "STOPPED":
        logger.info("SKIPPED batch_id=%s because it is disabled/stopped", batch_id)
        return 0

    script = CRON_FILES_DIR / batch["source_type"] / batch["script_name"]
    if not script.is_file():
        logger.error("Missing script: %s", script)
        db.mark_finished(batch_id, "FAILED", 2)
        return 2

    with db.connection() as lock_conn:
        if not db.try_advisory_lock(lock_conn, batch_id):
            logger.warning("SKIPPED duplicate execution batch_id=%s", batch_id)
            return 0

        started = datetime.now(timezone.utc)
        log_dir = EXECUTION_LOG_DIR / batch_id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{started.astimezone().strftime('%Y%m%d_%H%M%S')}.log"

        proc = None
        execution_id = None
        try:
            db.mark_started(batch_id)
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(f"START batch_id={batch_id} data_year={batch['data_year']}\n")
                fh.flush()
                max_attempts = 1 + int(batch["retry_count"])
                result = "FAILED"
                return_code = 1
                for attempt in range(1, max_attempts + 1):
                    fh.write(f"ATTEMPT {attempt}/{max_attempts}\n")
                    proc = subprocess.Popen(
                        [
                            PYTHON_BIN,
                            str(script),
                            "--year",
                            str(batch["data_year"]),
                            "--batch-id",
                            batch_id,
                        ],
                        cwd=str(BASE_DIR),
                        stdout=fh,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                        shell=False,
                        text=True,
                    )
                    execution_id = db.create_execution(
                        batch_id, started, proc.pid, str(log_file), attempt=attempt
                    )
                    try:
                        return_code = proc.wait(timeout=batch["timeout_seconds"])
                        result = "SUCCESS" if return_code == 0 else "FAILED"
                    except subprocess.TimeoutExpired:
                        result = "TIMEOUT"
                        _kill_process_tree(proc)
                        return_code = 124

                    db.finish_execution(execution_id, result, return_code)
                    fh.write(f"ATTEMPT_END {attempt} status={result} exit_code={return_code}\n")
                    if result == "SUCCESS":
                        break
                    if attempt < max_attempts:
                        fh.write("RETRYING\n")

                fh.write(f"END status={result} exit_code={return_code}\n")

            db.mark_finished(batch_id, result, return_code)
            logger.info("Finished batch_id=%s status=%s exit_code=%s", batch_id, result, return_code)
            return return_code if result != "SUCCESS" else 0
        except Exception as exc:
            logger.exception("Batch runner failure batch_id=%s", batch_id)
            if proc and proc.poll() is None:
                _kill_process_tree(proc)
            if execution_id is not None:
                db.finish_execution(execution_id, "FAILED", 1, str(exc))
            db.mark_finished(batch_id, "FAILED", 1)
            return 1
        finally:
            db.release_advisory_lock(lock_conn, batch_id)
            lock_conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="STEP Batch execution controller")
    parser.add_argument("--batch-id", required=True)
    args = parser.parse_args()
    return run(args.batch_id)


if __name__ == "__main__":
    raise SystemExit(main())
