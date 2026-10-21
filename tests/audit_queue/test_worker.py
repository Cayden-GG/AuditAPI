import threading
import time

import pytest

from app.audit_queue import worker as worker_module
from app.audit_queue.worker import QueueWorker, queue_worker


@pytest.fixture
def ticks(monkeypatch):
    """Fast intervals and recorders in place of the dispatcher and the watchdog"""
    state = type("State", (), {})()
    state.dispatches = []
    state.watchdogs = []
    state.dispatched = threading.Event()
    state.error = None

    def dispatcher(launcher):
        state.dispatches.append(launcher)
        state.dispatched.set()
        if state.error:
            raise state.error

    monkeypatch.setattr(worker_module, "start_dispatcher", dispatcher)
    monkeypatch.setattr(worker_module, "watchdog_timeouts", lambda: state.watchdogs.append(time.time()))
    monkeypatch.setattr(worker_module, "DISPATCH_INTERVAL_S", 0.01)
    monkeypatch.setattr(worker_module, "WATCHDOG_INTERVAL_S", 60)
    return state


def wait_for(condition, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture
def worker():
    instance = QueueWorker()
    yield instance
    instance.stop()


def test_the_worker_dispatches_jobs_repeatedly_with_the_thread_launcher(worker, ticks):
    worker.start()

    assert wait_for(lambda: len(ticks.dispatches) >= 3)
    assert all(launcher is worker_module.launch_job_in_thread for launcher in ticks.dispatches)


def test_the_watchdog_runs_immediately_then_waits_for_its_interval(worker, ticks):
    worker.start()

    assert wait_for(lambda: len(ticks.dispatches) >= 5)
    assert len(ticks.watchdogs) == 1


def test_the_watchdog_runs_again_after_its_interval(worker, ticks, monkeypatch):
    monkeypatch.setattr(worker_module, "WATCHDOG_INTERVAL_S", 0.03)

    worker.start()

    assert wait_for(lambda: len(ticks.watchdogs) >= 3)


def test_starting_twice_keeps_a_single_thread(worker, ticks):
    worker.start()
    first = worker._thread

    worker.start()

    assert worker._thread is first
    assert sum(t.name == first.name for t in threading.enumerate()) == 1


def test_stop_ends_the_thread_and_the_dispatching(worker, ticks):
    worker.start()
    assert ticks.dispatched.wait(2)

    worker.stop()

    assert not worker._thread.is_alive()
    count = len(ticks.dispatches)
    time.sleep(0.05)
    assert len(ticks.dispatches) == count


def test_stop_before_start_is_harmless():
    QueueWorker().stop()


def test_a_stopped_worker_does_not_restart_without_clearing_the_stop_flag(worker, ticks):
    worker.start()
    worker.stop()
    first = worker._thread

    worker.start()

    # the stop event is still set, so the new thread exits straight away
    assert worker._thread is not first
    worker._thread.join(timeout=1)
    assert not worker._thread.is_alive()


def test_the_module_exposes_one_shared_worker():
    assert isinstance(queue_worker, QueueWorker)


@pytest.mark.xfail(
    strict=True,
    reason="_run has no error handling, so one exception from the dispatcher (e.g. a locked database) ends the "
    "thread for good and queued jobs are never started until the server restarts",
)
def test_the_worker_keeps_going_after_a_dispatch_error(worker, ticks):
    ticks.error = RuntimeError("database is locked")
    worker.start()
    assert ticks.dispatched.wait(2)
    first_count = len(ticks.dispatches)

    time.sleep(0.1)

    assert len(ticks.dispatches) > first_count
