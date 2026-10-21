"""
Audit queue worker
Background thread that dispatches queued audit jobs and times out stuck ones
"""
import logging
import threading
import time

from .service import launch_job_in_thread, start_dispatcher, watchdog_timeouts

WATCHDOG_INTERVAL_S = 60
DISPATCH_INTERVAL_S = 5

logger = logging.getLogger(__name__)


class QueueWorker:
    """Background worker that polls the audit queue on a fixed cadence

    Dispatches queued jobs to free runner slots every DISPATCH_INTERVAL_S
    and runs the timeout watchdog every WATCHDOG_INTERVAL_S
    """
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Starts the worker thread, does nothing if it is already running"""
        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signals the worker thread to stop and waits up to 5 seconds for it to finish"""
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=5)

    @staticmethod
    def _safely(task, *args) -> None:
        """Runs a worker task, logging instead of raising so one failure (e.g. a locked database) cannot stop the worker"""
        try:
            task(*args)
        except Exception:
            logger.exception("Queue worker task %s failed.", getattr(task, "__name__", task))

    def _run(self) -> None:
        """Worker loop, polls the watchdog and dispatches jobs on a fixed cadence until stopped"""
        last_watchdog = 0.0
        while not self._stop_event.is_set():
            now = time.time()

            if now - last_watchdog >= WATCHDOG_INTERVAL_S:
                last_watchdog = now
                self._safely(watchdog_timeouts)

            self._safely(start_dispatcher, launch_job_in_thread)
            self._stop_event.wait(DISPATCH_INTERVAL_S)


queue_worker = QueueWorker()
