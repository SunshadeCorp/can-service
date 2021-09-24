#!/usr/bin/env python3
from typing import Any, Dict

import can
import paho.mqtt.client as mqtt

from can_byd_sim import CanBydSim
from can_storage import CanStorage


class CanService:
    def __init__(self):
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.mqtt_on_connect
        self.mqtt_client.on_message = self.mqtt_on_message

        try:
            self.can0 = can.interface.Bus(channel='can0', bustype='socketcan')
        except OSError as e:
            print(e)
            self.can0 = can.interface.Bus(channel='can0', bustype='virtual')

        self.storage = CanStorage()
        self.storage.overwrite_toggle()
        assert self.storage.overwrite is True
        self.can_byd_sim = CanBydSim(self.storage, self.can0)

        self.config = {
            'can': {
                'limits': {
                    'max_voltage': self.storage.message_infos[272][0],
                    'min_voltage': 'min voltage',  # TODO
                    'max_charge_current': 'max charge current',
                    'max_discharge_current': 'max discharge current',
                }
            }
        }

        self.mqtt_client.connect(host='127.0.0.1', port=1883, keepalive=60)

    def loop(self):
        self.mqtt_client.loop_forever(retry_first_connection=True)

    def loop_as_daemon(self):
        self.mqtt_client.loop_start()

    def mqtt_on_connect(self, client: mqtt.Client, userdata: Any, flags: Dict, rc: int):
        self.mqtt_client.subscribe('can/limits/max_voltage')
        self.mqtt_client.subscribe('can/limits/min_voltage')
        self.mqtt_client.subscribe('can/limits/max_charge_current')
        self.mqtt_client.subscribe('can/limits/max_discharge_current')
        self.mqtt_client.subscribe('master/relays/precharge')

    def mqtt_on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage):
        if msg.topic.startswith('master/relays/'):
            relay_number = msg.topic[msg.topic.find('/') + 1:msg.topic.rfind('/')]
            relay_number = relay_number[relay_number.find('/') + 1:]
            if relay_number.isnumeric():
                relay_number = int(relay_number)
                if relay_number in self.relays:
                    if msg.topic.endswith('/set') and len(msg.payload) > 0:
                        payload = msg.payload.decode()
                        if payload.lower() == 'on':
                            self.relays[relay_number].on()
                        elif payload.lower() == 'off':
                            self.relays[relay_number].off()
                    elif msg.topic.endswith('/status'):
                        self.relays[relay_number].publish_state()
            if msg.topic == 'master/relays/precharge':
                threading.Thread(name='precharge', target=self.precharge).start()


if __name__ == '__main__':
    can_service = CanService()
    can_service.loop()
