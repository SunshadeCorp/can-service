import threading
from typing import Callable


class CanThread:
    def __init__(self, name: str, target: Callable):
        self._name = name
        self._alive = False
        self.running = False
        self._target = target
        self._thread = None

    def start_thread(self):
        if not self._alive:
            self._thread = threading.Thread(name=self._name, target=self._run, daemon=True)
            self._thread.start()

    def stop_thread(self):
        if self._alive:
            self.running = False

    def start_stop_thread(self):
        if self._alive:
            self.stop_thread()
        else:
            self.start_thread()

    def _run(self):
        self._alive = True
        self.running = True
        self._target()
        self._alive = False

    def is_alive(self):
        return self._alive
