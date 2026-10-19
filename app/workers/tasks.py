"""Background worker wrapper for Qt QThreadPool with cancellation and progress signals."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    progress = Signal(int, str)
    result = Signal(object)
    error = Signal(str)
    cancelled = Signal()
    finished = Signal()


class CancellationToken:
    """Thread-safe cancellation flag passed to long-running background operations."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


class FunctionWorker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.token = CancellationToken()

    def cancel(self) -> None:
        self.token.cancel()

    @Slot()
    def run(self) -> None:
        try:
            if self.token.is_cancelled():
                self.signals.cancelled.emit()
                return
            out = self.fn(*self.args, **self.kwargs)
            if self.token.is_cancelled():
                self.signals.cancelled.emit()
            else:
                self.signals.result.emit(out)
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(f"{type(e).__name__}: {e}")
        finally:
            self.signals.finished.emit()
