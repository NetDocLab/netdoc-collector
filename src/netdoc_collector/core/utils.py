import yaml
from pathlib import Path
import shutil
from datetime import datetime, timezone
import logging

REPORT_PATH_FMT = '%Y%m%d-%H%M%S'


class LogListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        message = record.getMessage()
        if "Traceback" in message:
            # Do not store traceback
            return
        self.records.append(
            {
                "severity": record.levelname,
                "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "message": message,
            }
        )


def cleanup_old_snapshots(output_dir, retention):
    if output_dir and retention:
        base = Path(output_dir)
        snapshot_dirs = sorted(
            [d for d in base.iterdir() if d.is_dir() and is_valid_report_dir(d.name)],
            reverse=True,
        )
        for d in snapshot_dirs[retention:]:
            logging.info("Deleted snapshot directory %s", d)
            shutil.rmtree(d)


def load_config(path: str) -> dict:
    try:
        with open(path) as f:
            logging.info('Loading configuration from %s', path)
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.warning('Cannot load configuration from %s', path)
        pass
    return {}


def is_valid_report_dir(name):
    try:
        datetime.strptime(name, REPORT_PATH_FMT)
        return True
    except ValueError:
        return False
