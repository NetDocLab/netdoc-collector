"""Unit tests for shared collector utilities (logging collectors, config, cleanup)."""

import logging
import threading
import time

import pytest
import yaml

from netdoc_collector.core import utils as utils_module
from netdoc_collector.core.utils import (
    MainLogCollector,
    ThreadLogCollector,
    cleanup_old_snapshots,
    collect_task_logs,
    format_log_record,
    is_valid_report_dir,
    load_config,
)

# ─────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_root_logger_and_task_local():
    """Snapshot/restore root logger handlers and the shared thread-local flag.

    Without this, handlers attached by tests (or a failed context manager)
    would leak into other tests, and a stale `_task_local.active = True`
    would silently make MainLogCollector swallow records in later tests.
    """
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    had_active = hasattr(utils_module._task_local, 'active')
    original_active = getattr(utils_module._task_local, 'active', None)
    yield
    root.handlers = original_handlers
    root.setLevel(original_level)
    if had_active:
        utils_module._task_local.active = original_active
    elif hasattr(utils_module._task_local, 'active'):
        del utils_module._task_local.active


def _make_record(
    level=logging.INFO,
    msg='hello %s',
    args=('world',),
    exc_info=None,
    thread=None,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name='test',
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=exc_info,
    )
    if thread is not None:
        record.thread = thread
    return record


# ─────────────────────────────────────────────
#  MainLogCollector
# ─────────────────────────────────────────────


class TestMainLogCollector:
    def test_collects_records_when_not_inside_a_task(self):
        handler = MainLogCollector()
        record = _make_record()

        handler.emit(record)

        assert handler.records == [record]

    def test_skips_records_when_task_local_active(self):
        handler = MainLogCollector()
        utils_module._task_local.active = True
        record = _make_record()

        handler.emit(record)

        assert handler.records == []

    def test_resumes_collecting_after_task_local_cleared(self):
        handler = MainLogCollector()
        utils_module._task_local.active = True
        handler.emit(_make_record(msg='skipped'))
        utils_module._task_local.active = False
        handler.emit(_make_record(msg='collected'))

        assert len(handler.records) == 1
        assert handler.records[0].msg == 'collected'

    def test_drain_returns_and_clears_records(self):
        handler = MainLogCollector()
        handler.emit(_make_record())
        handler.emit(_make_record())

        drained = handler.drain()

        assert len(drained) == 2
        assert handler.records == []

    def test_drain_on_empty_collector_returns_empty_list(self):
        handler = MainLogCollector()
        assert handler.drain() == []

    def test_default_level_is_info(self):
        handler = MainLogCollector()
        assert handler.level == logging.INFO

    def test_attached_to_root_logger_receives_real_log_calls(self):
        """End-to-end: a real logger.info() call must reach the handler."""
        handler = MainLogCollector()
        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        try:
            logging.getLogger('some.module').info('hello from a real call')
        finally:
            root.removeHandler(handler)

        assert len(handler.records) == 1
        assert handler.records[0].getMessage() == 'hello from a real call'


# ─────────────────────────────────────────────
#  ThreadLogCollector
# ─────────────────────────────────────────────


class TestThreadLogCollector:
    def test_captures_own_thread_id_at_construction(self):
        handler = ThreadLogCollector()
        assert handler.thread_id == threading.get_ident()

    def test_collects_record_from_same_thread(self):
        handler = ThreadLogCollector()
        record = _make_record(thread=threading.get_ident())

        handler.emit(record)

        assert handler.records == [record]

    def test_ignores_record_from_a_different_thread(self):
        handler = ThreadLogCollector()
        record = _make_record(thread=threading.get_ident() + 1)

        handler.emit(record)

        assert handler.records == []

    def test_isolates_records_across_concurrent_threads(self):
        """Two ThreadLogCollectors on different threads must not cross-contaminate."""
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        results = {}

        def worker(name):
            handler = ThreadLogCollector()
            root.addHandler(handler)
            try:
                logging.getLogger('worker').info('message from %s', name)
                time.sleep(0.05)  # give the other thread a chance to log concurrently
                results[name] = [r.getMessage() for r in handler.records]
            finally:
                root.removeHandler(handler)

        t1 = threading.Thread(target=worker, args=('t1',))
        t2 = threading.Thread(target=worker, args=('t2',))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results['t1'] == ['message from t1']
        assert results['t2'] == ['message from t2']


# ─────────────────────────────────────────────
#  collect_task_logs
# ─────────────────────────────────────────────


class TestCollectTaskLogs:
    def test_yields_list_populated_with_records_emitted_inside(self):
        logging.getLogger().setLevel(logging.INFO)
        with collect_task_logs() as records:
            logging.getLogger('x').info('inside the context')

        assert len(records) == 1
        assert records[0].getMessage() == 'inside the context'

    def test_sets_task_local_active_during_context(self):
        assert not getattr(utils_module._task_local, 'active', False)
        with collect_task_logs():
            assert utils_module._task_local.active is True
        assert utils_module._task_local.active is False

    def test_task_local_reset_even_if_exception_raised_inside(self):
        with pytest.raises(RuntimeError), collect_task_logs():
            assert utils_module._task_local.active is True
            raise RuntimeError('boom')
        assert utils_module._task_local.active is False

    def test_handler_removed_from_root_logger_after_context(self):
        root = logging.getLogger()
        before = list(root.handlers)
        with collect_task_logs():
            assert len(root.handlers) == len(before) + 1
        assert root.handlers == before

    def test_records_emitted_after_context_are_not_captured(self):
        logging.getLogger().setLevel(logging.INFO)
        with collect_task_logs() as records:
            logging.getLogger('x').info('inside')
        logging.getLogger('x').info('outside')

        assert len(records) == 1
        assert records[0].getMessage() == 'inside'

    def test_makes_main_log_collector_skip_records_emitted_inside(self):
        job_collector = MainLogCollector()
        root = logging.getLogger()
        root.addHandler(job_collector)
        root.setLevel(logging.INFO)
        try:
            with collect_task_logs() as task_records:
                logging.getLogger('x').info('task-scoped message')
            logging.getLogger('x').info('job-scoped message')
        finally:
            root.removeHandler(job_collector)

        assert len(task_records) == 1
        assert task_records[0].getMessage() == 'task-scoped message'
        assert len(job_collector.records) == 1
        assert job_collector.records[0].getMessage() == 'job-scoped message'


# ─────────────────────────────────────────────
#  format_log_record
# ─────────────────────────────────────────────


class TestFormatLogRecord:
    def test_basic_fields(self):
        record = _make_record(level=logging.WARNING, msg='hello %s', args=('world',))

        entry = format_log_record(record)

        assert entry['level'] == 'WARNING'
        assert entry['message'] == 'hello world'
        assert entry['exception_type'] is None
        assert 'traceback' not in entry

    def test_includes_exception_type_and_traceback(self):
        try:
            raise ValueError('bad value')
        except ValueError:
            import sys

            exc_info = sys.exc_info()
            record = _make_record(level=logging.ERROR, msg='failed', args=(), exc_info=exc_info)

        entry = format_log_record(record)

        assert entry['exception_type'] == 'ValueError'
        assert 'traceback' in entry
        assert 'ValueError: bad value' in entry['traceback']

    def test_exc_info_present_but_no_exception_instance(self):
        """exc_info=(None, None, None) must not crash and must report no exception."""
        record = _make_record(
            level=logging.ERROR, msg='failed', args=(), exc_info=(None, None, None)
        )

        entry = format_log_record(record)

        assert entry['exception_type'] is None

    def test_exc_info_all_none_does_not_crash_on_traceback_formatting(self):
        """`if record.exc_info:` is True even for (None, None, None) — must not blow up."""
        record = _make_record(
            level=logging.ERROR, msg='failed', args=(), exc_info=(None, None, None)
        )

        entry = format_log_record(record)  # must not raise

        assert entry['exception_type'] is None


# ─────────────────────────────────────────────
#  cleanup_old_snapshots
# ─────────────────────────────────────────────


class TestCleanupOldSnapshots:
    def _make_snapshot_dirs(self, base, names):
        for name in names:
            (base / name).mkdir()

    def test_keeps_only_the_most_recent_snapshots(self, tmp_path):
        names = ['20240101-000000', '20240102-000000', '20240103-000000']
        self._make_snapshot_dirs(tmp_path, names)

        cleanup_old_snapshots(str(tmp_path), retention=2)

        remaining = {p.name for p in tmp_path.iterdir()}
        assert remaining == {'20240103-000000', '20240102-000000'}

    def test_ignores_non_report_directories(self, tmp_path):
        self._make_snapshot_dirs(tmp_path, ['20240101-000000', 'not-a-report-dir'])

        cleanup_old_snapshots(str(tmp_path), retention=0)

        remaining = {p.name for p in tmp_path.iterdir()}
        # retention=0 is falsy -> function is a no-op entirely
        assert remaining == {'20240101-000000', 'not-a-report-dir'}

    def test_ignores_regular_files(self, tmp_path):
        (tmp_path / '20240101-000000').mkdir()
        (tmp_path / 'readme.txt').write_text('not a dir')

        cleanup_old_snapshots(str(tmp_path), retention=0)

        assert (tmp_path / 'readme.txt').exists()

    def test_noop_when_output_dir_is_empty_string(self, tmp_path):
        # Falsy output_dir -> function returns without touching the filesystem.
        cleanup_old_snapshots('', retention=5)  # must not raise

    def test_noop_when_retention_is_zero(self, tmp_path):
        self._make_snapshot_dirs(tmp_path, ['20240101-000000'])
        cleanup_old_snapshots(str(tmp_path), retention=0)
        assert (tmp_path / '20240101-000000').exists()

    def test_retention_larger_than_snapshot_count_keeps_all(self, tmp_path):
        self._make_snapshot_dirs(tmp_path, ['20240101-000000', '20240102-000000'])
        cleanup_old_snapshots(str(tmp_path), retention=10)
        assert len(list(tmp_path.iterdir())) == 2


# ─────────────────────────────────────────────
#  load_config
# ─────────────────────────────────────────────


class TestLoadConfig:
    def test_loads_valid_yaml(self, tmp_path):
        path = tmp_path / 'config.yaml'
        path.write_text(yaml.dump({'workers': 5, 'output': './out'}))

        result = load_config(str(path))

        assert result == {'workers': 5, 'output': './out'}

    def test_missing_file_returns_empty_dict(self, tmp_path):
        result = load_config(str(tmp_path / 'does-not-exist.yaml'))
        assert result == {}

    def test_empty_file_returns_empty_dict(self, tmp_path):
        """Regression guard — see note below: yaml.safe_load('') returns None."""
        path = tmp_path / 'empty.yaml'
        path.write_text('')

        result = load_config(str(path))

        assert result == {}, (
            'load_config returned None for an empty YAML file instead of {} — '
            'callers doing cfg.get(...) on the result would raise AttributeError.'
        )


# ─────────────────────────────────────────────
#  is_valid_report_dir
# ─────────────────────────────────────────────


class TestIsValidReportDir:
    def test_valid_timestamp_format(self):
        assert is_valid_report_dir('20240315-142530') is True

    def test_invalid_format_returns_false(self):
        assert is_valid_report_dir('not-a-timestamp') is False

    def test_partial_timestamp_returns_false(self):
        assert is_valid_report_dir('20240315') is False

    def test_empty_string_returns_false(self):
        assert is_valid_report_dir('') is False
