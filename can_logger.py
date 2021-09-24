import can
import time
from pathlib import Path

from can_storage import CanStorage
from can_thread import CanThread


class CanLogger:
    def __init__(self, storage: CanStorage, can0: can.interface.Bus, can1: can.interface.Bus):
        self.sto = storage
        self.can0 = can0
        self.can1 = can1
        self.can0_to_can1 = CanThread('can0_to_can1', self.log_0_to_1)
        self.can1_to_can0 = CanThread('can1_to_can0', self.log_1_to_0)

    def start(self, can_read: can.interface.Bus, can_write: can.interface.Bus, can_thread: CanThread, file_prefix: str):
        folder = Path('/mnt/ssd/logs')
        logfile = folder / f'{file_prefix}_{time.time():.0f}.txt'
        with open(logfile, 'w') as file:
            while can_thread.running:
                try:
                    message = can_read.recv(0.1)
                except can.CanError as e:
                    print(f'can read failed: {e}')
                    continue
                if message is not None:
                    print(message)
                    print(message, file=file)
                    file.flush()
                    if self.sto.overwrite:
                        overwritten = False
                        with self.sto.overwrite_messages_lock:
                            for overwrite_message in self.sto.overwrite_messages:
                                if message.arbitration_id == overwrite_message['can_id']:
                                    message.data[overwrite_message['startbit']:overwrite_message['endbit']] = \
                                        overwrite_message['data']
                                    overwritten = True
                        if overwritten:
                            print(f'{message} <message overwrite>')
                    try:
                        can_write.send(message)
                    except can.CanError as e:
                        print(f'can write failed: {e}')
                    self.sto.process_message(message)

    def log_0_to_1(self):
        self.can0_to_can1.running = True
        self.start(self.can0, self.can1, self.can0_to_can1, self.can0_to_can1.name)
        self.can0_to_can1.running = False

    def log_1_to_0(self):
        self.can1_to_can0.running = True
        self.start(self.can1, self.can0, self.can1_to_can0, self.can1_to_can0.name)
        self.can1_to_can0.running = False
