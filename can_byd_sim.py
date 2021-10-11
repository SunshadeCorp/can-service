import can
import sched

from can_storage import CanStorage
from can_thread import CanThread
from can_service_events import CanServiceEvents


class CanBydSim:
    def __init__(self, storage: CanStorage, can_bus: can.interface.Bus, service_mode: bool = False):
        self.sto: CanStorage = storage
        self.can_bus: can.interface.Bus = can_bus
        self.scheduler: sched.scheduler = sched.scheduler()
        self.thread: CanThread = CanThread('byd-sim', self.run)
        self.events: CanServiceEvents = CanServiceEvents()
        self.service_mode: bool = service_mode

    def process_message(self, message: can.Message):
        print(message)
        if not self.service_mode:
            self.sto.process_message(message)
        self.events.on_received(message)
        if message.arbitration_id == 0x151:
            if message.data[0] == 0x1:
                messages = [(0x250, b'\x03\x16\x00\x66\x00\x33\x02\x09'),
                            (0x290, b'\x06\x37\x10\xd9\x00\x00\x00\x00'),
                            (0x2d0, b'\x00' + b'BYD' + b'\x00' * 4),
                            (0x3d0, b'\x00' + b'Battery'),
                            (0x3d0, b'\x01' + b'-Box Pr'),
                            (0x3d0, b'\x02' + b'emium H'),
                            (0x3d0, b'\x03' + b'VS' + b'\x00' * 5)]
                for message in messages:
                    can_message = can.Message(arbitration_id=message[0], data=message[1], is_extended_id=False)
                    if not self.service_mode:
                        self.sto.process_message(can_message)
                    try:
                        self.can_bus.send(can_message)
                        self.events.on_sent(can_message)
                    except can.CanError as e:
                        print(f'can write failed: {e}')

    def run(self):
        self.events.on_start()
        self.init_scheduler()
        if not self.service_mode:
            self.sto.load_message_infos()
        while self.thread.running:
            self.scheduler.run(blocking=False)
            try:
                message = self.can_bus.recv(0.1)
            except can.CanError as e:
                print(f'can read failed: {e}')
                continue
            if message is not None:
                self.process_message(message)
        list(map(self.scheduler.cancel, self.scheduler.queue))
        self.events.on_stop()

    def init_scheduler(self):
        self.scheduler.enter(2, 2, self.send_limits)
        self.scheduler.enter(10, 2, self.send_states)
        self.scheduler.enter(60, 2, self.send_alarm)
        self.scheduler.enter(10, 2, self.send_battery_info)
        self.scheduler.enter(10, 2, self.send_cell_info)

    @staticmethod
    def calculate_bytes(message_info: dict, value: float) -> bytearray:
        data = value * (1.0 / message_info['scaling'])
        data = int(data).to_bytes(message_info['length'], byteorder='big', signed=message_info['signed'])
        return bytearray(data)

    def calculate_message(self, can_id: int, initial_data=b'\x00' * 8) -> can.Message:
        data = bytearray(initial_data)
        if self.service_mode:
            if can_id in self.sto.message_infos:
                for startbit, message_info in self.sto.message_infos[can_id].items():
                    if 'overwrite' in message_info:
                        new_bytes = self.calculate_bytes(message_info, message_info['overwrite'])
                        data[startbit:message_info['endbit']] = new_bytes
        else:
            with self.sto.message_infos_lock:
                if can_id in self.sto.message_infos:
                    for startbit, message_info in self.sto.message_infos[can_id].items():
                        if self.sto.overwrite and 'overwrite' in message_info:
                            new_bytes = self.calculate_bytes(message_info, message_info['overwrite'])
                            data[startbit:message_info['endbit']] = new_bytes
        message = can.Message(arbitration_id=can_id, data=data, is_extended_id=False)
        if not self.service_mode:
            self.sto.process_message(message)
        return message

    def send_limits(self):
        message = self.calculate_message(0x110, b'\x09\x20\x06\x40\x01\x00\x01\x00')
        try:
            self.can_bus.send(message)
            self.events.on_sent(message)
        except can.CanError as e:
            print(f'can write failed: {e}')
        print(message)
        self.scheduler.enter(2, 1, self.send_limits)

    def send_states(self):
        message = self.calculate_message(0x150, b'\x26\x0c\x27\x10\x00\xf3\x00\xfa')
        try:
            self.can_bus.send(message)
            self.events.on_sent(message)
        except can.CanError as e:
            print(f'can write failed: {e}')
        print(message)
        self.scheduler.enter(10, 1, self.send_states)

    def send_alarm(self):
        message = self.calculate_message(0x190, b'\x00' * 3 + b'\x04' + b'\x00' * 4)
        try:
            self.can_bus.send(message)
            self.events.on_sent(message)
        except can.CanError as e:
            print(f'can write failed: {e}')
        print(message)
        self.scheduler.enter(60, 1, self.send_alarm)

    def send_battery_info(self):
        message = self.calculate_message(0x1d0, b'\x08\x49\x00\x00\x00\xb4\x03\x08')
        try:
            self.can_bus.send(message)
            self.events.on_sent(message)
        except can.CanError as e:
            print(f'can write failed: {e}')
        print(message)
        self.scheduler.enter(10, 1, self.send_battery_info)

    def send_cell_info(self):
        message = self.calculate_message(0x210, b'\x00\xbe\x00\xb4' + b'\x00' * 4)
        try:
            self.can_bus.send(message)
            self.events.on_sent(message)
        except can.CanError as e:
            print(f'can write failed: {e}')
        print(message)
        self.scheduler.enter(10, 1, self.send_cell_info)
