"""Shared helpers for configuration loading and report management.

This module provides utilities for snapshot cleanup, YAML configuration
loading, and structured log handling used across the collector.
"""

import logging
import shutil
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import yaml

_task_local = threading.local()

REPORT_PATH_FMT = '%Y%m%d-%H%M%S'


class MainLogCollector(logging.Handler):
    """Collect log records that do not belong to a per-host task.

    Task-level records are isolated and pushed per host by collect_task_logs.
    This handler captures the remaining records emitted while a job is in
    progress, including heartbeat and setup messages.
    """

    def __init__(self, level: int = logging.INFO):
        super().__init__(level=level)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(_task_local, 'active', False):
            # Already captured and pushed per-host by collect_task_logs.
            return
        self.records.append(record)

    def drain(self) -> list[logging.LogRecord]:
        """Return and clear all records collected so far."""
        records = self.records
        self.records = []
        return records


class ThreadLogCollector(logging.Handler):
    """Collect log records emitted by the calling thread only.

    This is safe for Nornir's threaded runner because each worker thread
    processes one host synchronously from start to finish.
    """

    def __init__(self, level=logging.INFO):
        super().__init__(level=level)
        self.thread_id = threading.get_ident()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread == self.thread_id:
            self.records.append(record)


@contextmanager
def collect_task_logs(level: int = logging.INFO):
    """Temporarily capture log records emitted by the calling thread.

    The current thread is marked as active for the duration of the context so
    that main log collection does not capture the same records twice.
    """
    handler = ThreadLogCollector(level=level)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    _task_local.active = True
    try:
        yield handler.records
    finally:
        _task_local.active = False
        root_logger.removeHandler(handler)


def format_log_record(record: logging.LogRecord) -> dict:
    """Convert a LogRecord into the payload shape expected by the backend."""
    entry = {
        'level': record.levelname,
        'message': record.getMessage(),
        'module': record.module,
        'func_name': record.funcName,
        'line_no': record.lineno,
        'process': record.process,
        'thread_name': record.threadName,
        'exception_type': type(record.exc_info[1]).__name__
        if record.exc_info and record.exc_info[1]
        else None,
    }
    if record.exc_info:
        import traceback

        entry['traceback'] = ''.join(traceback.format_exception(*record.exc_info))
    return entry


def cleanup_old_snapshots(output_dir, retention):
    """Remove snapshot directories older than the configured retention limit.

    Args:
        output_dir (str | Path): base directory containing snapshot folders.
        retention (int): number of latest snapshots to keep.
    """
    try:
        if output_dir and retention:
            base = Path(output_dir)
            snapshot_dirs = sorted(
                [d for d in base.iterdir() if d.is_dir() and is_valid_report_dir(d.name)],
                reverse=True,
            )
            for d in snapshot_dirs[retention:]:
                logging.info('Deleted snapshot directory %s', d)
                shutil.rmtree(d)
    except FileNotFoundError:
        pass


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
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logging.warning('Cannot load configuration from %s', path)
    return {}


def is_valid_report_dir(name):
    """Return True when a directory name matches the report timestamp format."""
    try:
        datetime.strptime(name, REPORT_PATH_FMT)
        return True
    except ValueError:
        return False
