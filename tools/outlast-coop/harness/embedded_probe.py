"""Late-join snapshot probe against a relay on <port> (room DEFAULT), fake peers only.
python -I embedded_probe.py <port>   prints: AUTO <n>  (pickup packets a late joiner gets without asking: the relay's snapshot queue, n = 1 when it is sent)
and TYPES 1 4  (1 = SPAWN, 4 = LOC) for what the joiner gets after a WORLD_REQUEST_ENEMIES."""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import relay_filter_test as rf  # noqa: E402

rf.PORT = int(sys.argv[1])


class P(rf.Peer):
    def __init__(self):
        super().__init__(room="DEFAULT")


owner = P()
owner.at(0)
owner.enemy(1, "OLEnemyProbe_0", bytes([8]) + b"OLEnemyX" + bytes(30))
owner.enemy(4, "OLEnemyProbe_0", bytes(30))
owner.send(5, 0x03, struct.pack("<iii", 7, 8, 9) + bytes([1]))   # PICKUP_STATE
time.sleep(0.5)
j = P()
auto = j.got_types(5, 1.5)
print("AUTO", 1 if 3 in auto else 0)
j.send(5, 0x0A)
print("TYPES", *sorted(j.got_types(3, 1.0)))
