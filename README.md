# can-service

## hardware

- Waveshare 2-CH CAN HAT ([shop](https://www.waveshare.com/2-ch-can-hat.htm)
  , [wiki](https://www.waveshare.com/wiki/2-CH_CAN_HAT))
- Raspberry Pi 4B

## installation

- follow [Enable SPI interface](https://www.waveshare.com/wiki/2-CH_CAN_HAT#Enable_SPI_interface)
- follow [Preparation](https://www.waveshare.com/wiki/2-CH_CAN_HAT#Preparation)
- get root with `sudo -i`
- `cd`
- `nano startscript.sh` and insert:

```bash
/usr/sbin/ip link set can0 type can restart-ms 100
/usr/sbin/ip link set can1 type can restart-ms 100
/usr/sbin/ip link set can0 up type can bitrate 500000
/usr/sbin/ip link set can1 up type can bitrate 500000
/usr/sbin/ifconfig can0 txqueuelen 100
/usr/sbin/ifconfig can1 txqueuelen 100
```

- `chmod +x startscript.sh`
- `sudo crontab -e` and add `@reboot /root/startscript.sh`
- (if running directly): run `pip install -r requirements.txt` in repository dir

## run

### directly

`./service.py`

### docker compose

```yaml
can-service:
  build: https://github.com/SunshadeCorp/can-service.git
  container_name: can-service
  depends_on:
    - mosquitto
  network_mode: host
  restart: unless-stopped
  volumes:
    - ./can-service/credentials.yaml:/usr/src/app/credentials.yaml:ro
```

## mqtt messages

publish:

```
master
└─ can (running/stopped)
   ├─ available (online/offline)
   └─ [topic] ([float])
```

subscribe:

```
master
├─ can
│  ├─ start ([any])
│  ├─ stop ([any])
│  └─ [topic]
│     ├─ reset ([any])
│     └─ set ([float])
└─ relays
   └─ kill_switch (pressed)
esp-total
├─ total_voltage ([float])
└─ total_current ([float]) {positive = discharge, negative = charge}
```

current `config.yaml` topics:

```
battery
├─ current {positive = charge, negative = discharge}
├─ max_cell_temp
├─ min_cell_temp
├─ soc
├─ soh
├─ temp
└─ voltage
inverter
├─ battery_voltage (read only)
├─ soc (read only)
└─ timestamp (read only)
limits
├─ max_charge_current
├─ max_discharge_current
├─ max_voltage
└─ min_voltage
```
