import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

from tests.conftest import _get_ios_device, skip_ios_device_tests

testbed = _get_ios_device()


class TestStandAloneCollector:
    """Execute the collector as a subprocess against the Cisco device."""

    @pytest.fixture()
    def workdir(self, tmp_path):
        config = {
            'cmd_timeout': 10,
            'output': './output',
            'retention': 2,
            'workers': 2,
            'inventory': './inventory.json',
            'backend': {
                'url': 'http://localhost:8000/',
                'verify': False,
                'timeout': 120,
                'token': None,
            },
        }
        (tmp_path / 'config.yaml').write_text(yaml.dump(config))
        (tmp_path / 'inventory.json').write_text(json.dumps(testbed['inventory']))
        return tmp_path

    def _run(self, workdir: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                '-m',
                'netdoc_collector',
                '-i',
                str(workdir / 'inventory.json'),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(workdir),
        )

    @pytest.mark.skipif(skip_ios_device_tests() is True, reason='Skip device related tests')
    def test_standalone_collector(self, workdir):

        r = self._run(workdir)
        assert r.returncode == 0

        # Verify output
        output_dir = Path(workdir) / Path('output')
        assert os.path.isdir(output_dir)

        # Verify output/20260615-170844
        today = date.today().strftime('%Y%m%d')
        matching_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith(today)]
        assert matching_dirs

        # Verify output/20260615-170844/192.168.0.1
        host_output_dir = matching_dirs[0] / Path(testbed['inventory']['all']['hosts'][0])
        assert os.path.isdir(host_output_dir)

        # Verify logs
        assert os.path.isfile(host_output_dir / Path('show-version.raw'))
        assert os.path.isfile(host_output_dir / Path('show-version.json'))
