import threading

import can


def can1_to_can0():
    try:
        with open('/media/pi/Intenso/can1_to_can0.txt', 'w') as f2:
            for msg2 in can1:
                print(msg2)
                print(msg2, file=f2)
                f2.flush()
                can0.send(msg2)
    except can.CanError as e2:
        print(f"failed {e2}")

# def test_dump(filename):
#     with open(filename) as file_in:
#         for line in file_in:
#             line = line[line.index('ID:') + 3:].strip()
#             id = line[:line.index(' ')]
#             id = bytes.fromhex(id)
#             id = int.from_bytes(id, byteorder='big', signed=False)
#             line = line[line.index(' '):].strip()
#             line = line[line.index('DLC') + 4:].strip()
#             line = line[line.index(' '):].strip()
#             line = line[:line.index('Channel')].strip()
#             line = bytes.fromhex(line)
#             message = can.Message(arbitration_id=id, data=line, is_extended_id=False)
#             if message.arbitration_id == 273:
#                 data = message.data[3]
#                 datahex = hex(data)
#                 print(1)
#     # print((test[2] * 0.5) - 40)
#     # print(struct.unpack('B', test)[0])

if __name__ == '__main__':
    # test_dump('logfile.txt')
    # pass

    can0 = can.interface.Bus(channel='can0', bustype='socketcan')
    can1 = can.interface.Bus(channel='can1', bustype='socketcan')

    t_can1_to_can0 = threading.Thread(name="can1_to_can0", target=can1_to_can0, daemon=True)
    t_can1_to_can0.start()
    try:
        with open('/media/pi/Intenso/can0_to_can1.txt', 'w') as f:
            for msg in can0:
                print(msg)
                print(msg, file=f)
                f.flush()
                can1.send(msg)
    except can.CanError as e:
        print(f"failed {e}")
