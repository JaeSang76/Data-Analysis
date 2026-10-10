from main.scheduler import _replace_managed_block
from main.config import CRON_BEGIN, CRON_END


def test_preserves_unmanaged_cron():
    old = "0 1 * * * backup.sh\n"
    new = _replace_managed_block(old, ["0 2 * * * job.sh"])
    assert "backup.sh" in new
    assert CRON_BEGIN in new
    assert CRON_END in new
    assert "job.sh" in new
