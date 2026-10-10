from main.schedule import build_cron_expressions


def test_daily_window():
    assert build_cron_expressions("DAILY", "02:00", "04:00", 60) == [
        "0 2 * * *", "0 3 * * *", "0 4 * * *"
    ]


def test_half_hour_window_does_not_overrun():
    assert build_cron_expressions("DAILY", "02:00", "04:00", 30) == [
        "0,30 2 * * *", "0,30 3 * * *", "0 4 * * *"
    ]


def test_weekday():
    assert build_cron_expressions("WEEKDAY", "02:00", "02:00", 1440) == ["0 2 * * 1-5"]


def test_weekly_sunday():
    assert build_cron_expressions("WEEKLY", "03:00", "03:00", 1440, weekday=6) == ["0 3 * * 0"]


def test_monthly():
    assert build_cron_expressions("MONTHLY", "04:00", "04:00", 1440, month_day=15) == ["0 4 15 * *"]
