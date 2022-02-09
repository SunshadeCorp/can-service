#!/bin/bash

/usr/sbin/ip link set can0 type can restart-ms 100
/usr/sbin/ip link set can1 type can restart-ms 100
/usr/sbin/ip link set can0 up type can bitrate 500000
/usr/sbin/ip link set can1 up type can bitrate 500000
/usr/sbin/ifconfig can0 txqueuelen 100
/usr/sbin/ifconfig can1 txqueuelen 100
