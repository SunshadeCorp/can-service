import can

if __name__ == '__main__':
    can0 = can.interface.Bus(channel='can0', bustype='socketcan')
    can1 = can.interface.Bus(channel='can1', bustype='socketcan')

    try:
        with open('logfile.txt', 'w') as f:
            for msg in can0:
                print(msg)
                print(msg, file=f)
                f.flush()
                can1.send(msg)
    except can.CanError as e:
        print(f"failed {e}")
