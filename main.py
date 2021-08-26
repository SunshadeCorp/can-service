#!/usr/bin/env python3
import sys
import threading
from datetime import datetime, timezone, timedelta, time
from pathlib import Path

import can
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QTableWidgetItem

from ui.main import Ui_MainWindow


class CanLogger:
    def __init__(self):
        try:
            self.can0 = can.interface.Bus(channel='can0', bustype='socketcan')
            self.can1 = can.interface.Bus(channel='can1', bustype='socketcan')
        except OSError as error:
            print(error)
        self.t_can0_to_can1 = threading.Thread(name="can0_to_can1", target=self.log_0_to_1, daemon=True)
        self.t_can0_to_can1_running = False
        self.t_can1_to_can0 = threading.Thread(name="can1_to_can0", target=self.log_1_to_0, daemon=True)
        self.t_can1_to_can0_running = False
        self.latest_messages = {}
        self.message_interval = {}

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

    def load_log(self, filename: str):
        with open(filename) as file:
            for line in file:
                message = self.log_line_to_message(line)
                if message.arbitration_id in self.latest_messages:
                    self.message_interval[message.arbitration_id] = message.timestamp - self.latest_messages[
                        message.arbitration_id].timestamp
                self.latest_messages[message.arbitration_id] = message

    @staticmethod
    def start(can_read: can.interface.Bus, can_write: can.interface.Bus, running: bool, file_prefix: str):
        # folder = Path('logs')
        folder = Path('/media/pi/Intenso/')
        logfile = folder / f'{file_prefix}_{time():.0f}.txt'
        try:
            with open(logfile, 'w') as file:
                while running:
                    message = can_read.recv(0.1)
                    if message is not None:
                        print(message)
                        print(message, file=file)
                        file.flush()
                        can_write.send(message)
        except can.CanError as error:
            print(f"failed {error}")

    def toggle_0_to_1(self):
        if self.t_can0_to_can1_running:
            self.t_can0_to_can1_running = False
        else:
            self.t_can0_to_can1.start()

    def toggle_1_to_0(self):
        if self.t_can1_to_can0_running:
            self.t_can1_to_can0_running = False
        else:
            self.t_can1_to_can0.start()

    def log_0_to_1(self):
        self.t_can0_to_can1_running = True
        self.start(self.can0, self.can1, self.t_can0_to_can1_running, 'can0_to_can1')
        self.t_can0_to_can1_running = False

    def log_1_to_0(self):
        self.t_can1_to_can0_running = True
        self.start(self.can1, self.can0, self.t_can1_to_can0_running, 'can1_to_can0')
        self.t_can1_to_can0_running = False


class MainWindow(Ui_MainWindow):

    def __init__(self):
        self.app = QtWidgets.QApplication(sys.argv)
        self.main_window = QtWidgets.QMainWindow()
        self.setupUi(self.main_window)

        self.can_logger = CanLogger()
        self.pushButtonCan0ToCan1.clicked.connect(self.can_logger.toggle_0_to_1)
        self.pushButtonCan1ToCan0.clicked.connect(self.can_logger.toggle_1_to_0)

        # self.can_logger.load_log('logs/can1_to_can0.txt')
        self.can_logger.load_log('logs/can0_to_can1.txt')
        self.tableWidgetMessages.clear()
        self.tableWidgetMessages.setRowCount(len(self.can_logger.latest_messages))
        labels = ['Timestamp', 'Time', 'ID Hex', 'ID Dec', 'Data', '0U16', '0S16', '1U16', '1S16', '2U16', '2S16',
                  '3U16', '3S16', '0U32', '0S32', '1U32', '1S32', 'Interval']
        self.tableWidgetMessages.setColumnCount(len(labels))
        self.tableWidgetMessages.setHorizontalHeaderLabels(labels)

        for i, latest_message in enumerate(sorted(self.can_logger.latest_messages)):
            message = self.can_logger.latest_messages[latest_message]
            self.tableWidgetMessages.setItem(i, labels.index('Timestamp'),
                                             QTableWidgetItem(f"{message.timestamp:>15.2f}"))
            timestamp = f'{datetime.fromtimestamp(message.timestamp):%H:%M:%S}'
            self.tableWidgetMessages.setItem(i, labels.index('Time'), QTableWidgetItem(timestamp))
            if message.is_extended_id:
                arbitration_id_string = f"{message.arbitration_id:08x}"
            else:
                arbitration_id_string = f"{message.arbitration_id:04x}"
            self.tableWidgetMessages.setItem(i, labels.index('ID Hex'), QTableWidgetItem(arbitration_id_string))
            self.tableWidgetMessages.setItem(i, labels.index('ID Dec'), QTableWidgetItem(str(message.arbitration_id)))
            data_strings = []
            if message.data is not None:
                for index in range(0, min(message.dlc, len(message.data))):
                    data_strings.append(f"{message.data[index]:02x}")
            self.tableWidgetMessages.setItem(i, labels.index('Data'), QTableWidgetItem(' '.join(data_strings)))
            value_1_u = int.from_bytes(message.data[0:2], byteorder="big", signed=False)
            value_1_s = int.from_bytes(message.data[0:2], byteorder="big", signed=True)
            value_2_u = int.from_bytes(message.data[2:4], byteorder="big", signed=False)
            value_2_s = int.from_bytes(message.data[2:4], byteorder="big", signed=True)
            value_3_u = int.from_bytes(message.data[4:6], byteorder="big", signed=False)
            value_3_s = int.from_bytes(message.data[4:6], byteorder="big", signed=True)
            value_4_u = int.from_bytes(message.data[6:8], byteorder="big", signed=False)
            value_4_s = int.from_bytes(message.data[6:8], byteorder="big", signed=True)
            self.tableWidgetMessages.setItem(i, labels.index('0U16'), QTableWidgetItem(str(value_1_u)))
            self.tableWidgetMessages.setItem(i, labels.index('0S16'), QTableWidgetItem(str(value_1_s)))
            self.tableWidgetMessages.setItem(i, labels.index('1U16'), QTableWidgetItem(str(value_2_u)))
            self.tableWidgetMessages.setItem(i, labels.index('1S16'), QTableWidgetItem(str(value_2_s)))
            self.tableWidgetMessages.setItem(i, labels.index('2U16'), QTableWidgetItem(str(value_3_u)))
            self.tableWidgetMessages.setItem(i, labels.index('2S16'), QTableWidgetItem(str(value_3_s)))
            self.tableWidgetMessages.setItem(i, labels.index('3U16'), QTableWidgetItem(str(value_4_u)))
            self.tableWidgetMessages.setItem(i, labels.index('3S16'), QTableWidgetItem(str(value_4_s)))

            value_1_u = int.from_bytes(message.data[0:4], byteorder="big", signed=False)
            value_1_s = int.from_bytes(message.data[0:4], byteorder="big", signed=True)
            value_2_u = int.from_bytes(message.data[4:8], byteorder="big", signed=False)
            value_2_s = int.from_bytes(message.data[4:8], byteorder="big", signed=True)
            self.tableWidgetMessages.setItem(i, labels.index('0U32'), QTableWidgetItem(str(value_1_u)))
            self.tableWidgetMessages.setItem(i, labels.index('0S32'), QTableWidgetItem(str(value_1_s)))
            self.tableWidgetMessages.setItem(i, labels.index('1U32'), QTableWidgetItem(str(value_2_u)))
            self.tableWidgetMessages.setItem(i, labels.index('1S32'), QTableWidgetItem(str(value_2_s)))

            if message.arbitration_id in self.can_logger.message_interval:
                interval = self.can_logger.message_interval[message.arbitration_id]
            else:
                interval = -1
            self.tableWidgetMessages.setItem(i, labels.index('Interval'), QTableWidgetItem(f'{interval:.0f}'))
        self.tableWidgetMessages.resizeColumnsToContents()

    def show(self):
        self.main_window.show()
        self.app.exec_()


def test_dump(filename: str):
    with open(filename) as file_in:
        for line in file_in:
            message = CanLogger.log_line_to_message(line)

            if message.arbitration_id == 0x111:
                message_id = hex(message.arbitration_id)
                timestamp = int.from_bytes(message.data[0:4], byteorder="big", signed=False)
                # print(f'{message_id} {timestamp} {datetime.fromtimestamp(timestamp, timezone(timedelta(hours=0)))}')
            elif message.arbitration_id == 0x91:
                # print(message)
                message_id = hex(message.arbitration_id)
                # battery_charge_voltage = int.from_bytes(message.data[0:2], byteorder="big", signed=False) * 0.1
                # dc_current_limit = int.from_bytes(message.data[2:4], byteorder="big", signed=True)
                # dc_discharge_current_limit = int.from_bytes(message.data[4:6], byteorder="big", signed=True) * 0.1
                # battery_discharge_voltage = int.from_bytes(message.data[6:8], byteorder="big", signed=False) * 0.1
                # print(f'{message} {message_id} {battery_charge_voltage}V {dc_current_limit}% {dc_discharge_current_limit}A {battery_discharge_voltage}V')
            elif message.arbitration_id == 0xd1:
                # print(message)
                # message_id = hex(message.arbitration_id)
                battery_charge_voltage = int.from_bytes(message.data[0:2], byteorder="big", signed=False)
                print(battery_charge_voltage)
                # dc_current_limit = int.from_bytes(message.data[2:4], byteorder="big", signed=True)
                # dc_discharge_current_limit = int.from_bytes(message.data[4:6], byteorder="big", signed=True) * 0.1
                # battery_discharge_voltage = int.from_bytes(message.data[6:8], byteorder="big", signed=False) * 0.1
                # print(f'{message} {message_id} {battery_charge_voltage}V {dc_current_limit}% {dc_discharge_current_limit}A {battery_discharge_voltage}V')

            elif message.arbitration_id == 0x110:
                timestamp = datetime.fromtimestamp(message.timestamp, timezone(timedelta(hours=0)))
                value_1 = int.from_bytes(message.data[0:2], byteorder="big", signed=False) * 0.1  # charge voltage
                value_2 = int.from_bytes(message.data[2:4], byteorder="big", signed=False) * 0.1  # discharge voltage
                value_3 = int.from_bytes(message.data[4:6], byteorder="big", signed=True) * 0.1  # charge current
                value_4 = int.from_bytes(message.data[6:8], byteorder="big", signed=True) * 0.1  # discharge current
                print(f'{timestamp} {message} {value_1:.1f}V {value_2}V {value_3}A {value_4}A ')
                # print(f' {message}')
            elif message.arbitration_id == 0x150:
                timestamp = datetime.fromtimestamp(message.timestamp, timezone(timedelta(hours=0)))
                # value_1 = int.from_bytes(message.data[0:2], byteorder="big", signed=False)  # 610 - 2870
                # value_2 = int.from_bytes(message.data[2:4], byteorder="big", signed=False)  # 10000
                # value_3 = int.from_bytes(message.data[4:6], byteorder="big", signed=False)  # SOC?
                # value_4 = int.from_bytes(message.data[6:8], byteorder="big", signed=False) * 0.1  # TEMP?
                # print(f'{timestamp} {message} {value_1:.1f} {value_2:.1f} {value_3:.1f} {value_4:.1f}')
                # print(f'{timestamp} {message}')
            # elif message.arbitration_id == 0x190:
            #     timestamp = datetime.fromtimestamp(message.timestamp, timezone(timedelta(hours=0)))
            #     # print(f'{timestamp} {message}')
            # elif message.arbitration_id == 0x1d0:
            #     timestamp = datetime.fromtimestamp(message.timestamp, timezone(timedelta(hours=0)))
            #     # print(f'{timestamp} {message}')
            # elif message.arbitration_id == 0x210:
            #     pass
            #     # print(f'{timestamp} {message}')
            # elif message.arbitration_id == 0x250:
            #     timestamp = datetime.fromtimestamp(message.timestamp, timezone(timedelta(hours=0)))
            #     # print(f'{timestamp} {message}')
            else:
                timestamp = datetime.fromtimestamp(message.timestamp, timezone(timedelta(hours=0)))
                value_1 = int.from_bytes(message.data[0:2], byteorder="big", signed=False) * 0.1
                value_2 = int.from_bytes(message.data[2:4], byteorder="big", signed=False) * 0.1
                value_3 = int.from_bytes(message.data[4:6], byteorder="big", signed=False) * 0.1
                value_4 = int.from_bytes(message.data[6:8], byteorder="big", signed=False) * 0.1
                # print(f'{timestamp} {message} {value_1:.1f} {value_2:.1f} {value_3:.1f} {value_4:.1f}')
                # print(message)
                # print(message.data.hex())
                message_id = hex(message.arbitration_id)
                # soc_value = int.from_bytes(message.data[0:2], byteorder="big", signed=False)
                # soh_value = int.from_bytes(message.data[2:4], byteorder="big", signed=False)
                # print(f'{message_id} SOC:{soc_value}% SOH:{soh_value}%')

                data = (message.data[0] << 8) | message.data[1]
                datahex = hex(data)
                databin = bin(data)

                message_id = hex(message.arbitration_id)
                battery_charge_voltage = int.from_bytes(message.data[0:2], byteorder="big", signed=False) * 0.1
                dc_current_limit = int.from_bytes(message.data[2:4], byteorder="big", signed=True) * 0.1
                dc_discharge_current_limit = int.from_bytes(message.data[4:6], byteorder="big", signed=True) * 0.1
                battery_discharge_voltage = int.from_bytes(message.data[6:8], byteorder="big", signed=False) * 0.1
                # print(f'{message_id} {battery_charge_voltage}V {dc_current_limit}A {dc_discharge_current_limit}A {battery_discharge_voltage}V')

    # print((test[2] * 0.5) - 40)
    # print(struct.unpack('B', test)[0])


if __name__ == '__main__':
    # test_dump('can0_to_can1.txt')
    # test_dump('logs/can1_to_can0.txt')

    main_window = MainWindow()
    main_window.show()
