#!/usr/bin/env python3
import can
import datetime
import json
import sys
from pathlib import Path
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QTableWidgetItem, QDialog, QMainWindow

from can_byd_sim import CanBydSim
from can_logger import CanLogger
from can_storage import CanStorage
from ui.main import Ui_MainWindow
from ui.values import Ui_Dialog


class ValuesDialog(Ui_Dialog):
    def __init__(self, parent: QMainWindow, storage: CanStorage):
        self.dialog = QDialog(parent, QtCore.Qt.WindowCloseButtonHint)
        self.setupUi(self.dialog)

        self.storage = storage

        self.pushButtonClose.clicked.connect(self.close_and_save)
        self.pushButtonInsert.clicked.connect(self.insert_row)
        self.pushButtonAutosize.clicked.connect(self.tableWidgetDisplay.resizeColumnsToContents)
        self.pushButtonDelete.clicked.connect(self.delete_row)
        self.pushButtonApply.clicked.connect(self.apply_config)

        self.labels = ['ID Hex', 'Startbit', 'Endbit', 'Signed', 'Scaling', 'Description', 'Value', 'Overwrite']
        self.tableWidgetDisplay.setColumnCount(len(self.labels))
        self.tableWidgetDisplay.setHorizontalHeaderLabels(self.labels)

        self.display_messages = []
        self.load_config()

        timer = QTimer(self.dialog)
        timer.timeout.connect(self.check_values)
        timer.start(1000)

        self.dialog.exec_()

    def apply_config(self):
        self.save_config()
        self.storage.reload_messages()

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

            with self.storage.dict_lock:
                if can_id in self.storage.latest_messages:
                    message = self.storage.latest_messages[can_id]
                    value = int.from_bytes(message.data[startbit:endbit], byteorder="big", signed=signed)
                    value = scaling * value
                    format_len = 0
                    if len(display_message['scaling']) > 2:
                        format_len = len(display_message['scaling']) - 2
                    self.tableWidgetDisplay.setItem(i, self.labels.index('Value'),
                                                    QTableWidgetItem(f'{value:.{format_len}f}'))


class MainWindow(Ui_MainWindow):

    def __init__(self):
        self.app = QtWidgets.QApplication(sys.argv)
        self.main_window = QtWidgets.QMainWindow()
        self.setupUi(self.main_window)

        try:
            self.can0 = can.interface.Bus(channel='can0', bustype='socketcan')
        except OSError as e:
            print(e)
            self.can0 = can.interface.Bus(channel='can0', bustype='virtual')
        try:
            self.can1 = can.interface.Bus(channel='can1', bustype='socketcan')
        except OSError as e:
            print(e)
            self.can1 = can.interface.Bus(channel='can1', bustype='virtual')

        self.storage = CanStorage()
        self.can_logger = CanLogger(self.storage, self.can0, self.can1)
        self.can_byd_sim = CanBydSim(self.storage, self.can0)
        self.pushButtonCan0ToCan1.clicked.connect(self.can_logger.can0_to_can1.start_stop_thread)
        self.pushButtonCan1ToCan0.clicked.connect(self.can_logger.can1_to_can0.start_stop_thread)
        self.pushButtonAutosize.clicked.connect(self.tableWidgetMessages.resizeColumnsToContents)
        self.pushButtonValues.clicked.connect(self.display_values)
        self.pushButtonOverwrite.clicked.connect(self.storage.overwrite_toggle)
        self.pushButtonBydsim.clicked.connect(self.can_byd_sim.thread.start_stop_thread)

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
            import glob
            for file in glob.glob('logs/*.txt'):
                self.storage.load_log(file)
            # self.storage.load_log('logs/can1_to_can0_1629553180.txt')
            # self.storage.load_log('logs/can0_to_can1_1629553179.txt')

    def show(self):
        self.main_window.show()
        self.app.exec_()

    def display_values(self):
        ValuesDialog(self.main_window, self.storage)

    def refresh_values(self):
        if self.can_logger.can0_to_can1.is_alive():
            self.pushButtonCan0ToCan1.setText(self.pushButtonCan0ToCan1.text().upper())
        else:
            self.pushButtonCan0ToCan1.setText(self.pushButtonCan0ToCan1.text().lower())
        if self.can_logger.can1_to_can0.is_alive():
            self.pushButtonCan1ToCan0.setText(self.pushButtonCan1ToCan0.text().upper())
        else:
            self.pushButtonCan1ToCan0.setText(self.pushButtonCan1ToCan0.text().lower())
        if self.can_byd_sim.thread.is_alive():
            self.pushButtonBydsim.setText(self.pushButtonBydsim.text().upper())
        else:
            self.pushButtonBydsim.setText(self.pushButtonBydsim.text().lower())
        if self.storage.overwrite:
            self.pushButtonOverwrite.setText(self.pushButtonOverwrite.text().upper())
        else:
            self.pushButtonOverwrite.setText(self.pushButtonOverwrite.text().lower())
        with self.storage.dict_lock:
            self.tableWidgetMessages.clear()
            self.tableWidgetMessages.setRowCount(len(self.storage.latest_messages))
            self.tableWidgetMessages.setColumnCount(len(self.labels))
            self.tableWidgetMessages.setHorizontalHeaderLabels(self.labels)
            for i, latest_message in enumerate(sorted(self.storage.latest_messages)):
                message = self.storage.latest_messages[latest_message]
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

                if message.arbitration_id in self.storage.message_interval:
                    interval = self.storage.message_interval[message.arbitration_id]
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
                try:
                    message = CanStorage.log_line_to_message(line)
                except ValueError:
                    print(file)
                id_dict[hex(message.arbitration_id)] = 1
                if message.arbitration_id == 0x3d0:
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
            message = CanStorage.log_line_to_message(line)

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
