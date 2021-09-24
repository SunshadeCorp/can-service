import threading
from typing import Callable


class CanThread:
    def __init__(self, name: str, target: Callable):
        self.name = name
        self.running = False
        self.target = target
        self.thread = threading.Thread(name=self.name, target=self.target, daemon=True)

    def start_stop_thread(self):
        if self.running:
            self.running = False
        elif not self.thread.is_alive():
            self.thread = threading.Thread(name=self.name, target=self.target, daemon=True)
            self.thread.start()

    def is_running(self):
        return self.running and self.thread.is_alive()
