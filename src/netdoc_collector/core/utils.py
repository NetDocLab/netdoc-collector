"""Utility helpers for configuration loading and report directory management.

This module provides shared utilities used by the collector, including
configuration loading, snapshot cleanup, and structured log record handling.
"""

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPORT_PATH_FMT = '%Y%m%d-%H%M%S'


class LogListHandler(logging.Handler):
    """Logging handler that captures structured messages for backend uploads.

    The handler stores messages in memory and omits traceback text to keep
    payloads concise.
    """

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        """Store the log record payload if it is not a traceback."""
        message = record.getMessage()
        if 'Traceback' in message:
            # Do not store traceback
            return
        self.records.append(
            {
                'severity': record.levelname,
                'timestamp': datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
                'message': message,
            }
        )


def cleanup_old_snapshots(output_dir, retention):
    """Remove snapshot directories older than the configured retention limit.

    Args:
        output_dir (str | Path): base directory containing snapshot folders.
        retention (int): number of latest snapshots to keep.
    """
    if output_dir and retention:
        base = Path(output_dir)
        snapshot_dirs = sorted(
            [d for d in base.iterdir() if d.is_dir() and is_valid_report_dir(d.name)],
            reverse=True,
        )
        for d in snapshot_dirs[retention:]:
            logging.info('Deleted snapshot directory %s', d)
            shutil.rmtree(d)


def load_config(path: str) -> dict:
    """Load YAML configuration from a file path.

    Args:
        path (str): filesystem path to a YAML config file.

    Returns:
        dict: parsed configuration, or an empty dict when the file is missing.
    """
    try:
        with open(path) as f:
            logging.info('Loading configuration from %s', path)
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.warning('Cannot load configuration from %s', path)
        pass
    return {}


def is_valid_report_dir(name):
    """Return True when a directory name matches the report timestamp format."""
    try:
        datetime.strptime(name, REPORT_PATH_FMT)
        return True
    except ValueError:
        return False
