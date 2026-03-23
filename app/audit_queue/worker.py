import threading
import time

from .service import launch_job_in_thread, start_dispatcher, watchdog_timeouts

WATCHDOG_INTERVAL_S = 60
DISPATCH_INTERVAL_S = 5


class QueueWorker:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        # Poll watchdog and dispatch jobs on a fixed cadence.
        last_watchdog = 0.0
        while not self._stop_event.is_set():
            now = time.time()
            if now - last_watchdog >= WATCHDOG_INTERVAL_S:
                watchdog_timeouts()
                last_watchdog = now
            start_dispatcher(launch_job_in_thread)
            self._stop_event.wait(DISPATCH_INTERVAL_S)


queue_worker = QueueWorker()
