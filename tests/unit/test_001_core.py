from datetime import datetime, timedelta
from pathlib import Path

from netdoc_collector.core.utils import (
    REPORT_PATH_FMT,
    cleanup_old_snapshots,
    is_valid_report_dir,
    load_config,
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


    def test_load_config_reads_yaml(self, tmp_path: Path):
        config_path = tmp_path / 'config.yaml'
        config_path.write_text('value: hello\nnumber: 42\n')

        data = load_config(str(config_path))

        assert data == {'value': 'hello', 'number': 42}


    def test_load_config_missing_file_returns_empty(self):
        data = load_config('does-not-exist.yaml')
        assert data == {}


    def test_is_valid_report_dir(self):
        assert is_valid_report_dir('20250101-000000')
        assert not is_valid_report_dir('not-a-timestamp')
        assert not is_valid_report_dir('2025-01-01')
