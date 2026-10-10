# STEP Batch Management System v1.0

## Scope
This implementation manages batch registration, modification, deletion, cron scheduling, stop/resume, execution state, execution history, locking, timeout, and logs.

It deliberately DOES NOT implement the actual data collection or analysis worker. Worker programs are external components under `cronFiles/API`, `cronFiles/DB`, `cronFiles/file`, or `cronFiles/webScraping` and will be integrated later for predictive/prescriptive analytics work.

## Directory

```text
/opt/stepBatch/
├── .env
├── venv/
├── main/
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── batch_manager.py
│   ├── scheduler.py
│   ├── schedule.py
│   ├── batch_runner.py
│   └── logger.py
├── cronFiles/
│   ├── API/
│   ├── DB/
│   ├── file/
│   └── webScraping/
├── logs/
│   ├── batch.log
│   └── execution/<batch_id>/*.log
├── runtime/
│   ├── locks/
│   ├── pid/
│   └── status/
├── config/
└── tests/
```

## Worker contract (integration boundary only)

A future worker should accept:

```bash
python worker.py --year 2026 --batch-id ENERGY_2026
```

The manager/runner does not know the worker's internal API/DB/file/web-scraping implementation. That implementation is intentionally outside this release.

## Installation on Ubuntu

```bash
sudo mkdir -p /opt/stepBatch
sudo cp -a . /opt/stepBatch/
cd /opt/stepBatch
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

Create a PostgreSQL database/user and set `DATABASE_URL` in `.env`.

Then initialize:

```bash
/opt/stepBatch/venv/bin/python -m main.main --init-db
```

Run the CLI:

```bash
/opt/stepBatch/venv/bin/python -m main.main
```

## Important operating rule

The crontab entries are managed only between:

```text
# STEP_BATCH_BEGIN
...
# STEP_BATCH_END
```

Existing unrelated user crontab entries are preserved.

The cron job invokes `batch_runner.py`, not a worker directly. The runner checks enabled/stopped state, acquires a PostgreSQL advisory lock, records execution history, redirects worker stdout/stderr to an execution log, applies timeout, and records the result.

## Security

- Run the manager and workers as a dedicated least-privileged Linux account, not root.
- Keep `.env` at mode 600 and out of Git.
- Worker file selection is limited to a filename inside one of the four approved source directories.
- `subprocess` uses argument lists and `shell=False`.
- Cron is installed for the account that owns the manager's crontab.

## Schedule semantics

For DAILY/WEEKDAY/WEEKLY/MONTHLY, `start_time` and `end_time` define an execution window and `interval_minutes` determines materialized cron times within that window. Cron has one-minute resolution. CUSTOM accepts a raw five-field cron expression.

A single long-running worker is prevented from being duplicated by a PostgreSQL advisory lock keyed by `batch_id`.
