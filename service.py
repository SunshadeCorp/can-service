#!/usr/bin/env python3
import can
import paho.mqtt.client as mqtt
import yaml
from pathlib import Path
from typing import Any, Dict

from can_byd_sim import CanBydSim
from can_storage import CanStorage


class CanService:
    def __init__(self):
        config = self.get_config('config.yaml')
        self.config = config['messages']
        credentials = self.get_config('credentials.yaml')

        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.mqtt_on_connect
        self.mqtt_client.on_message = self.mqtt_on_message

        try:
            self.can0 = can.interface.Bus(channel='can0', bustype='socketcan')
        except OSError as e:
            print(e)
            self.can0 = can.interface.Bus(channel='can0', bustype='virtual')

        self.storage = CanStorage()
        self.storage.message_infos = self.config
        self.can_byd_sim = CanBydSim(self.storage, self.can0, service_mode=True)
        self.can_byd_sim.events.on_start += self.can_start
        self.can_byd_sim.events.on_stop += self.can_stop
        self.can_byd_sim.events.on_sent += self.message_processed
        self.can_byd_sim.events.on_received += self.message_processed

        self.mqtt_client.username_pw_set(credentials['username'], credentials['password'])
        self.mqtt_client.will_set('master/can/available', 'offline', retain=True)
        self.mqtt_client.connect(host=config['mqtt_server'], port=config['mqtt_port'], keepalive=60)

        self.system_voltage: float = 170.0
        self.system_current: float = 0.0

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
                self.mqtt_client.publish(f"master/can/{entry['topic']}", value)
            break

    def mqtt_on_connect(self, client: mqtt.Client, userdata: Any, flags: Dict, rc: int):
        self.mqtt_client.subscribe('master/can/start')
        self.mqtt_client.subscribe('master/can/stop')
        for can_id in self.config:
            for start_bit in self.config[can_id]:
                entry: Dict = self.config[can_id][start_bit]
                if 'topic' in entry:
                    if not entry.get('read_only', False):
                        self.mqtt_client.subscribe(f"master/can/{entry['topic']}/set")
        self.mqtt_client.subscribe('esp-module/1/total_system_voltage')
        self.mqtt_client.subscribe('esp-module/4/total_system_current')
        self.mqtt_client.publish('master/can', 'running' if self.can_byd_sim.thread.running else 'stopped')
        self.mqtt_client.publish('master/can/available', 'online', retain=True)

    def mqtt_on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage):
        if msg.topic == 'master/can/start' and not self.can_byd_sim.thread.running:
            self.can_byd_sim.thread.start_stop_thread()
        elif msg.topic == 'master/can/stop' and self.can_byd_sim.thread.running:
            self.can_byd_sim.thread.start_stop_thread()
        elif msg.topic == 'esp-module/1/total_system_voltage':
            self.system_voltage = float(msg.payload)
            self.config[464][0]['overwrite'] = self.system_voltage
            return
        elif msg.topic == 'esp-module/4/total_system_current':
            self.system_current = float(msg.payload)
            self.config[464][2]['overwrite'] = self.system_current * -1.0
            return
        for can_id in self.config:
            for start_bit in self.config[can_id]:
                entry: Dict = self.config[can_id][start_bit]
                if 'topic' in entry and f"master/can/{entry['topic']}/set" == msg.topic:
                    try:
                        payload = float(msg.payload)
                    except ValueError:
                        break
                    self.config[can_id][start_bit]['overwrite'] = payload
                    break


if __name__ == '__main__':
    can_service = CanService()
    can_service.loop()
