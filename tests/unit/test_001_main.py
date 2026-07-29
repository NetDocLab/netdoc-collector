from datetime import datetime, timedelta
from pathlib import Path

from netdoc_collector.core.utils import (
    REPORT_PATH_FMT,
    cleanup_old_snapshots,
)


class TestMain:
    def test_cleanup_old_snapshots_keeps_most_recent(self, tmp_path: Path):
        base = tmp_path
        names = []
        for i in range(5):
            ts = datetime(2025, 1, 1, 0, 0, 0) + timedelta(days=i)
            dir_name = ts.strftime(REPORT_PATH_FMT)
            (base / dir_name).mkdir()
            names.append(dir_name)
        (base / 'invalid-dir').mkdir()

        cleanup_old_snapshots(base, retention=2)

        remaining = sorted([p.name for p in base.iterdir() if p.is_dir()])
        assert remaining == [names[-2], names[-1], 'invalid-dir']
