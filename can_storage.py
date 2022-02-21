import can
import json
import threading
from pathlib import Path


class CanStorage:
    def __init__(self):
        self.dict_lock = threading.Lock()
        self.latest_messages = {}
        self.message_interval = {}
        self.overwrite = False
        self.overwrite_messages = []
        self.overwrite_messages_lock = threading.Lock()
        self.message_infos = {}
        self.message_infos_lock = threading.Lock()

    @staticmethod
    def log_line_to_message(line: str) -> can.Message:
        line = line[line.index('Timestamp:') + 10:].strip()
        timestamp = line[:line.index(' ')]
        line = line[line.index('ID:') + 3:].strip()
        can_id = line[:line.index(' ')]
        can_id = bytes.fromhex(can_id)
        can_id = int.from_bytes(can_id, byteorder='big', signed=False)
        line = line[line.index(' '):].strip()
        line = line[line.index('DLC') + 4:].strip()
        line = line[line.index(' '):].strip()
        line = line[:line.index('Channel')].strip()
        line = bytes.fromhex(line)
        return can.Message(timestamp=float(timestamp), arbitration_id=can_id, data=line, is_extended_id=False)

    def load_log(self, filename: str):
        with open(filename) as file:
            for line in file:
                self.process_message(self.log_line_to_message(line))

    def overwrite_toggle(self) -> bool:
        self.overwrite = not self.overwrite
        if self.overwrite:
            self.reload_messages()
        return self.overwrite

    def reload_messages(self):
        self.load_overwrite_messages()
        self.load_message_infos()

    def process_message(self, message: can.Message):
        with self.dict_lock:
            if message.arbitration_id in self.latest_messages:
                self.message_interval[message.arbitration_id] = message.timestamp - self.latest_messages[
                    message.arbitration_id].timestamp
            self.latest_messages[message.arbitration_id] = message

    def load_overwrite_messages(self):
        if Path('display.json').is_file():
            with self.overwrite_messages_lock:
                with open('display.json', 'r') as f:
                    self.overwrite_messages = json.load(f)
                self.overwrite_messages[:] = [message for message in self.overwrite_messages if
                                              len(message['overwrite']) > 0]
                for i, overwrite_message in enumerate(self.overwrite_messages):
                    can_id = bytes.fromhex(self.overwrite_messages[i]['can_id_hex'])
                    can_id = int.from_bytes(can_id, byteorder='big', signed=False)
                    self.overwrite_messages[i]['can_id'] = can_id
                    self.overwrite_messages[i]['startbit'] = int(self.overwrite_messages[i]['startbit'])
                    self.overwrite_messages[i]['endbit'] = int(self.overwrite_messages[i]['endbit'])
                    signed = bool(int(self.overwrite_messages[i]['signed']))
                    data = float(self.overwrite_messages[i]['overwrite']) * (
                            1.0 / float(self.overwrite_messages[i]['scaling']))
                    data = int(data).to_bytes(
                        self.overwrite_messages[i]['endbit'] - self.overwrite_messages[i]['startbit'],
                        byteorder='big',
                        signed=signed)
                    self.overwrite_messages[i]['data'] = data

    def load_message_infos(self):
        with self.message_infos_lock:
            self.message_infos = {}
            if Path('display.json').is_file():
                with open('display.json', 'r') as f:
                    message_infos = json.load(f)
                for i, message_info in enumerate(message_infos):
                    can_id = bytes.fromhex(message_infos[i]['can_id_hex'])
                    can_id = int.from_bytes(can_id, byteorder='big', signed=False)
                    if can_id not in self.message_infos:
                        self.message_infos[can_id] = {}
                    startbit = int(message_infos[i]['startbit'])
                    if startbit not in self.message_infos:
                        self.message_infos[can_id][startbit] = {}
                    endbit = int(message_infos[i]['endbit'])
                    self.message_infos[can_id][startbit]['endbit'] = endbit
                    self.message_infos[can_id][startbit]['length'] = endbit - startbit
                    self.message_infos[can_id][startbit]['signed'] = bool(int(message_infos[i]['signed']))
                    self.message_infos[can_id][startbit]['scaling'] = float(message_infos[i]['scaling'])
                    if len(message_infos[i]['overwrite']) > 0:
                        self.message_infos[can_id][startbit]['overwrite'] = float(message_infos[i]['overwrite'])
