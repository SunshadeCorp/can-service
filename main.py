#!/usr/bin/env python3
import json
import sched
import sys
import threading
import datetime
import time
from pathlib import Path
from typing import Callable

import can
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QTableWidgetItem, QDialog, QMainWindow

from ui.values import Ui_Dialog
from ui.main import Ui_MainWindow


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


class CanBydSim:
    def __init__(self):
        try:
            self.can0 = can.interface.Bus(channel='can0', bustype='socketcan')
        except OSError as error:
            print(error)
            self.can0 = can.interface.Bus(channel='can0', bustype='virtual')
        self.scheduler = sched.scheduler()
        self.name = 'byd-sim'
        self.running = False
        self.overwrite = False
        self.thread = threading.Thread(name=self.name, target=self.run, daemon=True)
        self.message_infos = {}
        self.message_infos_lock = threading.Lock()

    def overwrite_toggle(self):
        if self.overwrite:
            self.overwrite = False
        else:
            self.load_message_infos()
            self.overwrite = True

    def start_stop(self):
        if self.running:
            self.running = False
        elif not self.thread.is_alive():
            print('start thread')
            self.thread = threading.Thread(name=self.name, target=self.run, daemon=True)
            self.thread.start()

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
                    self.message_infos[can_id][startbit]['signed'] = bool(message_infos[i]['signed'])
                    self.message_infos[can_id][startbit]['scaling'] = float(message_infos[i]['scaling'])
                    if len(message_infos[i]['overwrite']) > 0:
                        self.message_infos[can_id][startbit]['overwrite'] = float(message_infos[i]['overwrite'])

    def process_message(self, message: can.Message):
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
                    self.can0.send(can.Message(arbitration_id=message[0], data=message[1], is_extended_id=False))

    def run(self):
        self.running = True
        self.init_scheduler()
        self.load_message_infos()
        while self.running:
            self.scheduler.run(blocking=False)
            try:
                message = self.can0.recv(0.1)
            except can.CanError as e:
                print(f'can read failed: {e}')
                continue
            if message is not None:
                self.process_message(message)
        self.running = False

    def is_running(self) -> bool:
        return self.running and self.thread.is_alive()

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
        with self.message_infos_lock:
            if can_id in self.message_infos:
                for startbit, message_info in self.message_infos[can_id].items():
                    if self.overwrite and 'overwrite' in message_info:
                        new_bytes = self.calculate_bytes(message_info, message_info['overwrite'])
                        data[startbit:message_info['endbit']] = new_bytes
        return can.Message(arbitration_id=can_id, data=data, is_extended_id=False)

    def send_limits(self):
        message = self.calculate_message(0x110, b'\x09\x20\x06\x40\x01\x00\x01\x00')
        self.can0.send(message)
        print(message)
        self.scheduler.enter(2, 1, self.send_limits)

    def send_states(self):
        message = self.calculate_message(0x150, b'\x26\x0c\x27\x10\x00\xf3\x00\xfa')
        self.can0.send(message)
        print(message)
        self.scheduler.enter(10, 1, self.send_states)

    def send_alarm(self):
        message = self.calculate_message(0x190, b'\x00' * 3 + b'\x04' + b'\x00' * 4)
        self.can0.send(message)
        print(message)
        self.scheduler.enter(60, 1, self.send_alarm)

    def send_battery_info(self):
        message = self.calculate_message(0x1d0, b'\x08\x49\x00\x00\x00\xb4\x03\x08')
        self.can0.send(message)
        print(message)
        self.scheduler.enter(10, 1, self.send_battery_info)

    def send_cell_info(self):
        message = self.calculate_message(0x210, b'\x00\xbe\x00\xb4' + b'\x00' * 4)
        self.can0.send(message)
        print(message)
        self.scheduler.enter(10, 1, self.send_cell_info)


class CanLogger:
    def __init__(self):
        try:
            self.can0 = can.interface.Bus(channel='can0', bustype='socketcan')
            self.can1 = can.interface.Bus(channel='can1', bustype='socketcan')
        except OSError as error:
            print(error)
            self.can0 = can.interface.Bus(channel='can0', bustype='virtual')
            self.can1 = can.interface.Bus(channel='can1', bustype='virtual')
        self.can0_to_can1 = CanThread('can0_to_can1', self.log_0_to_1)
        self.can1_to_can0 = CanThread('can1_to_can0', self.log_1_to_0)
        self.dict_lock = threading.Lock()
        self.latest_messages = {}
        self.message_interval = {}
        self.overwrite = False
        self.overwrite_messages = []
        self.overwrite_messages_lock = threading.Lock()

    def overwrite_toggle(self):
        if self.overwrite:
            self.overwrite = False
        elif Path('display.json').is_file():
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
                    signed = bool(self.overwrite_messages[i]['signed'])
                    data = float(self.overwrite_messages[i]['overwrite']) * (
                            1.0 / float(self.overwrite_messages[i]['scaling']))
                    data = int(data).to_bytes(
                        self.overwrite_messages[i]['endbit'] - self.overwrite_messages[i]['startbit'], byteorder='big',
                        signed=signed)
                    self.overwrite_messages[i]['data'] = data
            self.overwrite = True

    @staticmethod
    def log_line_to_message(line: str) -> can.Message:
        line = line[line.index('Timestamp:') + 10:].strip()
        timestamp = line[:line.index(' ')]
        line = line[line.index('ID:') + 3:].strip()
        id = line[:line.index(' ')]
        id = bytes.fromhex(id)
        id = int.from_bytes(id, byteorder='big', signed=False)
        line = line[line.index(' '):].strip()
        line = line[line.index('DLC') + 4:].strip()
        line = line[line.index(' '):].strip()
        line = line[:line.index('Channel')].strip()
        line = bytes.fromhex(line)
        return can.Message(timestamp=float(timestamp), arbitration_id=id, data=line, is_extended_id=False)

    def process_message(self, message: can.Message):
        with self.dict_lock:
            if message.arbitration_id in self.latest_messages:
                self.message_interval[message.arbitration_id] = message.timestamp - self.latest_messages[
                    message.arbitration_id].timestamp
            self.latest_messages[message.arbitration_id] = message

    def load_log(self, filename: str):
        with open(filename) as file:
            for line in file:
                self.process_message(self.log_line_to_message(line))

    def start(self, can_read: can.interface.Bus, can_write: can.interface.Bus, can_thread: CanThread, file_prefix: str):
        # folder = Path('logs')
        folder = Path('/media/pi/Intenso/')
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
                    if self.overwrite:
                        overwritten = False
                        with self.overwrite_messages_lock:
                            for overwrite_message in self.overwrite_messages:
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
                    self.process_message(message)

    def log_0_to_1(self):
        self.can0_to_can1.running = True
        self.start(self.can0, self.can1, self.can0_to_can1, self.can0_to_can1.name)
        self.can0_to_can1.running = False

    def log_1_to_0(self):
        self.can1_to_can0.running = True
        self.start(self.can1, self.can0, self.can1_to_can0, self.can1_to_can0.name)
        self.can1_to_can0.running = False


class ValuesDialog(Ui_Dialog):
    def __init__(self, parent: QMainWindow, can_logger: CanLogger):
        self.dialog = QDialog(parent, QtCore.Qt.WindowCloseButtonHint)
        self.setupUi(self.dialog)

        self.can_logger = can_logger

        self.pushButtonClose.clicked.connect(self.close_and_save)
        self.pushButtonInsert.clicked.connect(self.insert_row)
        self.pushButtonAutosize.clicked.connect(self.autosize_table)
        self.pushButtonDelete.clicked.connect(self.delete_row)

        self.labels = ['ID Hex', 'Startbit', 'Endbit', 'Signed', 'Scaling', 'Description', 'Value', 'Overwrite']
        self.tableWidgetDisplay.setColumnCount(len(self.labels))
        self.tableWidgetDisplay.setHorizontalHeaderLabels(self.labels)

        self.display_messages = []
        self.load_config()

        timer = QTimer(self.dialog)
        timer.timeout.connect(self.check_values)
        timer.start(1000)

        self.dialog.exec_()

    def delete_row(self):
        self.tableWidgetDisplay.removeRow(self.tableWidgetDisplay.currentRow())

    def load_config(self):
        if Path('display.json').is_file():
            with open('display.json', 'r') as f:
                self.display_messages = json.load(f)
            self.tableWidgetDisplay.clear()
            self.tableWidgetDisplay.setHorizontalHeaderLabels(self.labels)
            for i, display_message in enumerate(self.display_messages):
                self.tableWidgetDisplay.insertRow(i)

                self.tableWidgetDisplay.setItem(i, self.labels.index('ID Hex'),
                                                QTableWidgetItem(display_message['can_id_hex']))
                self.tableWidgetDisplay.setItem(i, self.labels.index('Startbit'),
                                                QTableWidgetItem(display_message['startbit']))
                self.tableWidgetDisplay.setItem(i, self.labels.index('Endbit'),
                                                QTableWidgetItem(display_message['endbit']))
                self.tableWidgetDisplay.setItem(i, self.labels.index('Signed'),
                                                QTableWidgetItem(display_message['signed']))
                self.tableWidgetDisplay.setItem(i, self.labels.index('Scaling'),
                                                QTableWidgetItem(display_message['scaling']))
                self.tableWidgetDisplay.setItem(i, self.labels.index('Description'),
                                                QTableWidgetItem(display_message['description']))
                self.tableWidgetDisplay.setItem(i, self.labels.index('Overwrite'),
                                                QTableWidgetItem(display_message['overwrite']))

    def close_and_save(self):
        self.save_config()
        self.dialog.close()

    def save_config(self):
        with open('display.json', 'w') as f:
            json.dump(self.display_messages, f, sort_keys=True)

    def insert_row(self):
        self.tableWidgetDisplay.insertRow(self.tableWidgetDisplay.rowCount())

    def check_values(self):
        self.display_messages.clear()
        for i in range(0, self.tableWidgetDisplay.rowCount()):
            display_message = {}

            can_id_hex_item = self.tableWidgetDisplay.item(i, self.labels.index('ID Hex'))
            if can_id_hex_item is None:
                continue
            can_id_hex = can_id_hex_item.text()
            display_message['can_id_hex'] = can_id_hex
            try:
                can_id = bytes.fromhex(can_id_hex)
            except ValueError:
                continue
            can_id = int.from_bytes(can_id, byteorder='big', signed=False)

            startbit = self.tableWidgetDisplay.item(i, self.labels.index('Startbit'))
            if startbit is None:
                continue
            startbit = startbit.text()
            display_message['startbit'] = startbit
            if not startbit.isnumeric():
                continue
            startbit = int(startbit)

            endbit = self.tableWidgetDisplay.item(i, self.labels.index('Endbit'))
            if endbit is None:
                continue
            endbit = endbit.text()
            display_message['endbit'] = endbit
            if not endbit.isnumeric():
                continue
            endbit = int(endbit)

            signed = self.tableWidgetDisplay.item(i, self.labels.index('Signed'))
            if signed is None:
                continue
            signed = signed.text()
            display_message['signed'] = signed
            if not signed.isnumeric():
                continue
            signed = bool(signed)

            scaling = self.tableWidgetDisplay.item(i, self.labels.index('Scaling'))
            if scaling is None:
                continue
            scaling = scaling.text()
            display_message['scaling'] = scaling
            try:
                scaling = float(scaling)
            except ValueError:
                continue

            description = self.tableWidgetDisplay.item(i, self.labels.index('Description'))
            if description is None:
                description = ''
            else:
                description = description.text()
            display_message['description'] = description

            overwrite = self.tableWidgetDisplay.item(i, self.labels.index('Overwrite'))
            if overwrite is None:
                overwrite = ''
            else:
                overwrite = overwrite.text()
                try:
                    float(overwrite)
                except ValueError:
                    overwrite = ''
            display_message['overwrite'] = overwrite

            self.display_messages.append(display_message)

            with self.can_logger.dict_lock:
                if can_id in self.can_logger.latest_messages:
                    message = self.can_logger.latest_messages[can_id]
                    value = int.from_bytes(message.data[startbit:endbit], byteorder="big", signed=signed)
                    value = scaling * value
                    format_len = 0
                    if len(display_message['scaling']) > 2:
                        format_len = len(display_message['scaling']) - 2
                    self.tableWidgetDisplay.setItem(i, self.labels.index('Value'),
                                                    QTableWidgetItem(f'{value:.{format_len}f}'))

    def autosize_table(self):
        self.tableWidgetDisplay.resizeColumnsToContents()


class MainWindow(Ui_MainWindow):

    def __init__(self):
        self.app = QtWidgets.QApplication(sys.argv)
        self.main_window = QtWidgets.QMainWindow()
        self.setupUi(self.main_window)

        self.can_logger = CanLogger()
        # self.can_byd_sim = CanBydSim()
        # self.can_byd_sim.start_stop()
        self.pushButtonCan0ToCan1.clicked.connect(self.can_logger.can0_to_can1.start_stop_thread)
        self.pushButtonCan1ToCan0.clicked.connect(self.can_logger.can1_to_can0.start_stop_thread)
        self.pushButtonAutosize.clicked.connect(self.autosize_table)
        self.pushButtonValues.clicked.connect(self.display_values)
        self.pushButtonOverwrite.clicked.connect(self.overwrite_toggle)

        self.labels = ['Timestamp', 'Time', 'ID Hex', 'ID Dec', 'Data', '0U16', '0S16', '1U16', '1S16', '2U16', '2S16',
                       '3U16', '3S16', '0U32', '0S32', '1U32', '1S32', 'Interval', 'Channel']
        self.refresh_values()
        self.tableWidgetMessages.resizeColumnsToContents()

        timer = QTimer(self.main_window)
        timer.timeout.connect(self.refresh_values)
        timer.start(1000)

        if sys.platform.startswith("linux"):
            self.main_window.showMaximized()
        else:
            pass
            # self.can_logger.load_log('logs/can1_to_can0.txt')
            # self.can_logger.load_log('logs/can0_to_can1.txt')
            # self.can_logger.load_log('logs/logfile.txt')

    def overwrite_toggle(self):
        self.can_logger.overwrite_toggle()
        self.can_byd_sim.overwrite_toggle()

    def show(self):
        self.main_window.show()
        self.app.exec_()

    def display_values(self):
        ValuesDialog(self.main_window, self.can_logger)

    def autosize_table(self):
        self.tableWidgetMessages.resizeColumnsToContents()

    def refresh_values(self):
        if self.can_logger.can0_to_can1.is_running():
            self.pushButtonCan0ToCan1.setText(self.pushButtonCan0ToCan1.text().upper())
        else:
            self.pushButtonCan0ToCan1.setText(self.pushButtonCan0ToCan1.text().lower())
        if self.can_logger.can1_to_can0.is_running():
            self.pushButtonCan1ToCan0.setText(self.pushButtonCan1ToCan0.text().upper())
        else:
            self.pushButtonCan1ToCan0.setText(self.pushButtonCan1ToCan0.text().lower())
        if self.can_logger.overwrite:
            self.pushButtonOverwrite.setText(self.pushButtonOverwrite.text().upper())
        else:
            self.pushButtonOverwrite.setText(self.pushButtonOverwrite.text().lower())
        with self.can_logger.dict_lock:
            self.tableWidgetMessages.clear()
            self.tableWidgetMessages.setRowCount(len(self.can_logger.latest_messages))
            self.tableWidgetMessages.setColumnCount(len(self.labels))
            self.tableWidgetMessages.setHorizontalHeaderLabels(self.labels)
            for i, latest_message in enumerate(sorted(self.can_logger.latest_messages)):
                message = self.can_logger.latest_messages[latest_message]
                self.tableWidgetMessages.setItem(i, self.labels.index('Timestamp'),
                                                 QTableWidgetItem(f"{message.timestamp:>15.2f}"))
                timestamp = f'{datetime.datetime.fromtimestamp(message.timestamp):%H:%M:%S}'
                self.tableWidgetMessages.setItem(i, self.labels.index('Time'), QTableWidgetItem(timestamp))
                if message.is_extended_id:
                    arbitration_id_string = f"{message.arbitration_id:08x}"
                else:
                    arbitration_id_string = f"{message.arbitration_id:04x}"
                self.tableWidgetMessages.setItem(i, self.labels.index('ID Hex'),
                                                 QTableWidgetItem(arbitration_id_string))
                self.tableWidgetMessages.setItem(i, self.labels.index('ID Dec'),
                                                 QTableWidgetItem(str(message.arbitration_id)))
                data_strings = []
                if message.data is not None:
                    for index in range(0, min(message.dlc, len(message.data))):
                        data_strings.append(f"{message.data[index]:02x}")
                self.tableWidgetMessages.setItem(i, self.labels.index('Data'), QTableWidgetItem(' '.join(data_strings)))
                value_1_u = int.from_bytes(message.data[0:2], byteorder="big", signed=False)
                value_1_s = int.from_bytes(message.data[0:2], byteorder="big", signed=True)
                value_2_u = int.from_bytes(message.data[2:4], byteorder="big", signed=False)
                value_2_s = int.from_bytes(message.data[2:4], byteorder="big", signed=True)
                value_3_u = int.from_bytes(message.data[4:6], byteorder="big", signed=False)
                value_3_s = int.from_bytes(message.data[4:6], byteorder="big", signed=True)
                value_4_u = int.from_bytes(message.data[6:8], byteorder="big", signed=False)
                value_4_s = int.from_bytes(message.data[6:8], byteorder="big", signed=True)
                self.tableWidgetMessages.setItem(i, self.labels.index('0U16'), QTableWidgetItem(str(value_1_u)))
                self.tableWidgetMessages.setItem(i, self.labels.index('0S16'), QTableWidgetItem(str(value_1_s)))
                self.tableWidgetMessages.setItem(i, self.labels.index('1U16'), QTableWidgetItem(str(value_2_u)))
                self.tableWidgetMessages.setItem(i, self.labels.index('1S16'), QTableWidgetItem(str(value_2_s)))
                self.tableWidgetMessages.setItem(i, self.labels.index('2U16'), QTableWidgetItem(str(value_3_u)))
                self.tableWidgetMessages.setItem(i, self.labels.index('2S16'), QTableWidgetItem(str(value_3_s)))
                self.tableWidgetMessages.setItem(i, self.labels.index('3U16'), QTableWidgetItem(str(value_4_u)))
                self.tableWidgetMessages.setItem(i, self.labels.index('3S16'), QTableWidgetItem(str(value_4_s)))

                value_1_u = int.from_bytes(message.data[0:4], byteorder="big", signed=False)
                value_1_s = int.from_bytes(message.data[0:4], byteorder="big", signed=True)
                value_2_u = int.from_bytes(message.data[4:8], byteorder="big", signed=False)
                value_2_s = int.from_bytes(message.data[4:8], byteorder="big", signed=True)
                self.tableWidgetMessages.setItem(i, self.labels.index('0U32'), QTableWidgetItem(str(value_1_u)))
                self.tableWidgetMessages.setItem(i, self.labels.index('0S32'), QTableWidgetItem(str(value_1_s)))
                self.tableWidgetMessages.setItem(i, self.labels.index('1U32'), QTableWidgetItem(str(value_2_u)))
                self.tableWidgetMessages.setItem(i, self.labels.index('1S32'), QTableWidgetItem(str(value_2_s)))

                if message.arbitration_id in self.can_logger.message_interval:
                    interval = self.can_logger.message_interval[message.arbitration_id]
                else:
                    interval = -1
                self.tableWidgetMessages.setItem(i, self.labels.index('Interval'), QTableWidgetItem(f'{interval:.0f}'))
                self.tableWidgetMessages.setItem(i, self.labels.index('Channel'),
                                                 QTableWidgetItem(f'{message.channel}'))


def test_multiple_logs(start_name: str):
    result = list(Path('logs').rglob(f'{start_name}*.txt'))
    id_dict = {}
    byte_dict = {}
    for file in result:
        # test_log(str(file))
        with open(file) as file_in:
            for line in file_in:
                message = CanLogger.log_line_to_message(line)
                id_dict[hex(message.arbitration_id)] = 1
                if message.arbitration_id == 0x1d0:
                    for i in range(8):
                        if i not in byte_dict:
                            print(message)
                            byte_dict[i] = {}
                        byte_dict[i][message.data[i]] = 1
                        # byte_dict[i][hex(message.data[i])] = 1
                        # byte_dict[i][bin(message.data[i])] = 1
                        # if message.data[i] != 0:
                        #     print(f'not null {i}, {hex(message.data[i - 1])} {hex(message.data[i])}')
                    for i in range(4):
                        if 2 * i + 10 not in byte_dict:
                            byte_dict[2 * i + 10] = {}
                            byte_dict[2 * i + 11] = {}
                        value_u = int.from_bytes(message.data[2 * i:2 * i + 2], byteorder="big", signed=False)
                        value_s = int.from_bytes(message.data[2 * i:2 * i + 2], byteorder="big", signed=True)
                        byte_dict[2 * i + 10][value_u] = 1
                        byte_dict[2 * i + 11][value_s] = 1
    for pos in byte_dict:
        print(f'{pos} {len(byte_dict[pos])} >> {min(byte_dict[pos])} {max(byte_dict[pos])}')
    for can_id in id_dict:
        print(can_id)
    # print(byte_dict)


def test_log(filename: str):
    with open(filename) as file_in:
        byte_dict = {}
        for line in file_in:
            message = CanLogger.log_line_to_message(line)

            if message.arbitration_id == 0x150:
                for i in range(8):
                    if i not in byte_dict:
                        byte_dict[i] = {}
                    byte_dict[i][message.data[i]] = 1
                    # if message.data[i] != 0:
                    #     print(f'not null {i}, {hex(message.data[i - 1])} {hex(message.data[i])}')
        print(byte_dict)
        # print(message)
        # message_id = hex(message.arbitration_id)
        # timestamp = int.from_bytes(message.data[0:4], byteorder="big", signed=False)
        # print(f'{message_id} {timestamp} {datetime.fromtimestamp(timestamp, timezone(timedelta(hours=0)))}')


if __name__ == '__main__':
    # test_multiple_logs('can0_to_can1')
    # test_multiple_logs('can1_to_can0')
    # test_log('can0_to_can1.txt')
    # test_log('logs/can1_to_can0.txt')

    main_window = MainWindow()
    main_window.show()
