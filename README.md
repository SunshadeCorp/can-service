# can-service

The CAN service is built for Waveshares 2 channel CAN hat:
https://www.waveshare.com/2-ch-can-hat.htm

Information on how the can hat is used is found here:
https://www.waveshare.com/wiki/2-CH_CAN_HAT

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
│     └─ set ([float])
└─ relays
   └─ kill_switch (pressed)
esp-module
├─ 1
│  └─ total_system_voltage ([float])
└─ 4
   └─ total_system_current ([int, float])
```

current config.yaml topics:

```
battery
├─ current
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
