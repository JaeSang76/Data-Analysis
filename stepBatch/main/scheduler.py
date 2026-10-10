from __future__ import annotations

import subprocess
from dataclasses import dataclass

from .config import CRON_BEGIN, CRON_END, CRONTAB_BIN, PYTHON_BIN, BASE_DIR


@dataclass
class CronResult:
    returncode: int
    stdout: str
    stderr: str


def _run(args: list[str], input_text: str | None = None) -> CronResult:
    completed = subprocess.run(
        args,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    return CronResult(completed.returncode, completed.stdout, completed.stderr)


def read_crontab() -> str:
    result = _run([CRONTAB_BIN, "-l"])
    # crontab -l commonly returns non-zero when the user has no crontab.
    if result.returncode != 0 and "no crontab" not in result.stderr.lower():
        raise RuntimeError(result.stderr.strip() or "crontab -l failed")
    return result.stdout


def _managed_block(existing: str) -> list[str]:
    lines = existing.splitlines()
    try:
        start = lines.index(CRON_BEGIN)
        end = lines.index(CRON_END, start + 1)
    except ValueError:
        return []
    return lines[start : end + 1]


def _replace_managed_block(existing: str, entries: list[str]) -> str:
    lines = existing.splitlines()
    try:
        start = lines.index(CRON_BEGIN)
        end = lines.index(CRON_END, start + 1)
        before = lines[:start]
        after = lines[end + 1 :]
    except ValueError:
        before = lines
        after = []

    managed = [CRON_BEGIN, *entries, CRON_END]
    result = [*before, *managed, *after]
    return "\n".join(result).rstrip() + "\n"


def build_command(batch_id: str) -> str:
    runner = BASE_DIR / "main" / "batch_runner.py"
    return f"cd {BASE_DIR} && {PYTHON_BIN} -m main.batch_runner --batch-id {batch_id}"


def install_batch_cron(batch_id: str, cron_expression: str) -> None:
    existing = read_crontab()
    entries = [
        line for line in _managed_block(existing)
        if not line.endswith(f"--batch-id {batch_id}")
    ]
    for expression in cron_expression.splitlines():
        expression = expression.strip()
        if expression:
            entries.append(f"{expression} {build_command(batch_id)}")
    _write_crontab(_replace_managed_block(existing, entries))


def remove_batch_cron(batch_id: str) -> None:
    existing = read_crontab()
    block = _managed_block(existing)
    if not block:
        return
    entries = [line for line in block[1:-1] if not line.endswith(f"--batch-id {batch_id}")]
    if entries:
        _write_crontab(_replace_managed_block(existing, entries))
    else:
        lines = existing.splitlines()
        start = lines.index(CRON_BEGIN)
        end = lines.index(CRON_END, start + 1)
        result = [*lines[:start], *lines[end + 1 :]]
        _write_crontab("\n".join(result).rstrip() + ("\n" if result else ""))


def _write_crontab(content: str) -> None:
    result = _run([CRONTAB_BIN, "-"], input_text=content)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "crontab installation failed")


def managed_crons() -> list[str]:
    block = _managed_block(read_crontab())
    return block[1:-1] if block else []
