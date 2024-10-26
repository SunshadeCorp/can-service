#!/usr/bin/env python3
from pathlib import Path
from typing import Any, Dict

import can
import paho.mqtt.client as mqtt
import yaml

from can_byd_sim import CanBydSim
from can_storage import CanStorage


class CanService:
    def __init__(self):
        config = self.get_config('config.yaml')
        self.total_system_voltage_topic = config.get('total_system_voltage_topic', 'esp-total/total_voltage')
        self.total_system_current_topic = config.get('total_system_current_topic', 'esp-total/total_current')
        self.config = config['messages']
        self.init_config()
        credentials = self.get_config('credentials.yaml')

        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self.mqtt_on_connect
        self.mqtt_client.on_message = self.mqtt_on_message

        try:
            self.can0 = can.interface.Bus(channel='can0', interface='socketcan')
        except OSError as e:
            print(e)
            self.can0 = can.interface.Bus(channel='can0', interface='virtual')

        self.storage = CanStorage()
        self.storage.message_infos = self.config
        self.can_byd_sim = CanBydSim(self.storage, self.can0, service_mode=True)
        self.can_byd_sim.events.on_start += self.can_start
        self.can_byd_sim.events.on_stop += self.can_stop
        self.can_byd_sim.events.on_sent += self.message_processed
        self.can_byd_sim.events.on_received += self.message_processed

        self.mqtt_client.username_pw_set(credentials['username'], credentials['password'])
        self.mqtt_client.will_set('master/can/available', 'offline', retain=True)
        self.mqtt_client.connect(host=config['mqtt_server'], port=config['mqtt_port'])

        self.can_byd_sim.thread.start_stop_thread()

    def init_config(self):
        for can_id in self.config:
            for start_bit in self.config[can_id]:
                entry: Dict = self.config[can_id][start_bit]
                if 'overwrite' in entry:
                    entry['default_overwrite'] = entry['overwrite']

    @staticmethod
    def get_config(filename: str) -> Dict:
        with open(Path(__file__).parent / filename, 'r') as file:
            try:
                config = yaml.safe_load(file)
                print(config)
                return config
            except yaml.YAMLError as e:
                print(e)

    def loop(self):
        self.mqtt_client.loop_forever(retry_first_connection=True)

    def loop_as_daemon(self):
        self.mqtt_client.loop_start()

    def can_start(self):
        self.mqtt_client.publish('master/can', 'running')

    def can_stop(self):
        self.mqtt_client.publish('master/can', 'stopped')

    def message_processed(self, message: can.Message):
        for can_id in self.config:
            if can_id != message.arbitration_id:
                continue
            for start_bit in self.config[can_id]:
                entry: Dict = self.config[can_id][start_bit]
                value = int.from_bytes(message.data[start_bit:entry['endbit']], byteorder="big", signed=entry['signed'])
                value = entry['scaling'] * value
                self.mqtt_client.publish(f"master/can/{entry['topic']}", f'{value:.2f}')
            break

    def set_overwrite_by_topic(self, topic: str, value: float) -> bool:
        for can_id in self.config:
            for start_bit in self.config[can_id]:
                entry: Dict = self.config[can_id][start_bit]
                if 'topic' in entry and entry['topic'] == topic:
                    self.config[can_id][start_bit]['overwrite'] = value
                    return True
        return False

    def mqtt_on_connect(self, client, userdata, flags, reason_code, properties):
        self.mqtt_client.subscribe('master/can/start')
        self.mqtt_client.subscribe('master/can/stop')
        for can_id in self.config:
            for start_bit in self.config[can_id]:
                entry: Dict = self.config[can_id][start_bit]
                if 'topic' in entry:
                    if not entry.get('read_only', False):
                        self.mqtt_client.subscribe(f"master/can/{entry['topic']}/set")
                        self.mqtt_client.subscribe(f"master/can/{entry['topic']}/reset")
        self.mqtt_client.subscribe(self.total_system_voltage_topic)
        self.mqtt_client.subscribe(self.total_system_current_topic)
        self.mqtt_client.subscribe('master/relays/kill_switch')
        self.mqtt_client.publish('master/can', 'running' if self.can_byd_sim.thread.is_alive() else 'stopped',
                                 retain=True)
        self.mqtt_client.publish('master/can/available', 'online', retain=True)

    def mqtt_on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage):
        if msg.topic == 'master/can/start':
            self.can_byd_sim.thread.start_thread()
            return
        elif msg.topic == 'master/can/stop':
            self.can_byd_sim.thread.stop_thread()
            return
        elif msg.topic == 'master/relays/kill_switch':
            if msg.payload.decode() == 'pressed':
                self.set_overwrite_by_topic('limits/max_voltage', 0.0)
                self.set_overwrite_by_topic('limits/min_voltage', 0.0)
                self.set_overwrite_by_topic('limits/max_discharge_current', 0.0)
                self.set_overwrite_by_topic('limits/max_charge_current', 0.0)
            return
        elif msg.topic == self.total_system_voltage_topic:
            try:
                system_voltage = float(msg.payload)
            except ValueError:
                return
            self.set_overwrite_by_topic('battery/voltage', system_voltage)
            return
        elif msg.topic == self.total_system_current_topic:
            try:
                system_current = float(msg.payload) * -1
            except ValueError:
                return
            self.set_overwrite_by_topic('battery/current', system_current)
            return
        for can_id in self.config:
            for start_bit in self.config[can_id]:
                entry: Dict = self.config[can_id][start_bit]
                if 'topic' in entry:
                    if f"master/can/{entry['topic']}/set" == msg.topic:
                        try:
                            payload = float(msg.payload)
                        except ValueError:
                            break
                        entry['overwrite'] = payload
                        break
                    elif f"master/can/{entry['topic']}/reset" == msg.topic:
                        if 'default_overwrite' in entry:
                            entry['overwrite'] = entry['default_overwrite']


if __name__ == '__main__':
    can_service = CanService()
    can_service.loop()
