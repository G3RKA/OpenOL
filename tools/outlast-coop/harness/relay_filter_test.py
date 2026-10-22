"""Protocol test for the relay's --trigger-radius filter. No game needed (about 15 s).

  python -I relay_filter_test.py <patched_relay.exe> <upstream_relay.exe>

Starts the relay on UDP 17791 and joins four fake peers to room PUBLIC:
  S (sender) at x=0, NEAR at x=500, FAR at x=5000, BLIND (never sent a hero position).
Prints  RESULT: PASS|FAIL <name>  per check and a SUMMARY; exit code 0 only if every check passes.

  T1  radius 1000: a trigger from S reaches NEAR and BLIND (fail open), not FAR
  T2  radius 0 (off): a trigger reaches everybody (upstream behaviour kept)
  T3  radius 1000: door packets are NOT filtered (FAR still gets them)
  T4  twin: the same expectation as T1 against the UPSTREAM relay must be violated (proves T1 can fail)
  T5  radius 1000: a sender with no known position reaches everybody (fail open)
  T6  late join: the joiner's enemy snapshot contains SPAWN and LOC (patched relay)
  T7  twin: on the upstream relay the snapshot has SPAWN but no LOC (ENEMY_LOC is 0x08 there, the client sends 0x04)
Wire format: [channel][type][player_id LE4][payload]; HERO_STATE needs >= 18 bytes (position floats at byte 6).
"""
import os
import socket
import struct
import subprocess
import sys
import time

PORT = 17791
CH_SRV, CH_HERO, CH_DOOR, CH_WORLD = 0, 1, 2, 5
results = []


def check(name, ok, why=""):
    results.append(ok)
    print(f"RESULT: {'PASS' if ok else 'FAIL'} {name} {why}".rstrip(), flush=True)


class Peer:
    def __init__(self, room="PUBLIC"):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if hasattr(socket, "SIO_UDP_CONNRESET"):
            self.s.ioctl(socket.SIO_UDP_CONNRESET, False)
        self.s.settimeout(0.3)
        self.pid = None
        for _ in range(10):
            self.s.sendto(f"HELLO,{room},\n".encode(), ("127.0.0.1", PORT))
            try:
                d, _ = self.s.recvfrom(65535)
            except socket.timeout:
                continue
            if d[0] == 0xE0:
                self.pid = struct.unpack_from("<I", d, 5)[0]
                break
        if self.pid is None:
            raise SystemExit("peer could not join the relay")

    def send(self, ch, typ, payload=b""):
        self.s.sendto(bytes([ch, typ]) + struct.pack("<I", self.pid) + payload, ("127.0.0.1", PORT))

    def at(self, x):
        self.send(CH_HERO, 0x01, struct.pack("<fff", x, 0.0, 0.0) + bytes(30))

    def trigger(self):
        p = b"lvl.TheWorld:PersistentLevel.Main_Sequence.SeqEvent_Touch_1"
        self.send(CH_WORLD, 0x01, struct.pack("<i", 0) + bytes([len(p)]) + p)

    def door(self):
        self.send(CH_DOOR, 0x04, struct.pack("<iii", 1, 2, 3))

    def enemy(self, typ, name, extra=b""):
        n = name.encode()
        self.send(3, typ, bytes([len(n)]) + n + extra)

    def got_types(self, ch, window=1.0):
        """Set of packet types received on channel `ch` during `window` seconds."""
        end, seen = time.time() + window, set()
        while time.time() < end:
            try:
                d, _ = self.s.recvfrom(65535)
            except socket.timeout:
                continue
            if len(d) >= 2 and d[0] == ch:
                seen.add(d[1])
        return seen

    def got(self, ch, typ, window=1.0):
        end = time.time() + window
        n = 0
        while time.time() < end:
            try:
                d, _ = self.s.recvfrom(65535)
            except socket.timeout:
                continue
            if len(d) >= 2 and d[0] == ch and d[1] == typ:
                n += 1
        return n


def run_relay(exe, extra):
    p = subprocess.Popen([exe, "--port", str(PORT), "--ip", "127.0.0.1", "--name", "FilterTest", *extra], cwd=os.path.dirname(exe),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    return p


def scenario(exe, extra, fn):
    p = run_relay(exe, extra)
    try:
        S, NEAR, FAR, BLIND = Peer(), Peer(), Peer(), Peer()
        S.at(0)
        NEAR.at(500)
        FAR.at(5000)          # BLIND never sends a hero state
        time.sleep(0.5)
        for peer in (S, NEAR, FAR, BLIND):   # drain join-time snapshots
            peer.got(CH_HERO, 0x01, 0.3)
        return fn(S, NEAR, FAR, BLIND)
    finally:
        p.kill()
        time.sleep(0.5)


def main():
    patched, upstream = sys.argv[1], sys.argv[2]

    def t1(S, NEAR, FAR, BLIND):
        S.trigger()
        return NEAR.got(CH_WORLD, 1), FAR.got(CH_WORLD, 1, 0.4), BLIND.got(CH_WORLD, 1, 0.4)

    near, far, blind = scenario(patched, ["--trigger-radius", "1000"], t1)
    check("T1.radius-on-near-and-blind-get-it-far-does-not", near == 1 and blind == 1 and far == 0, f"near={near} blind={blind} far={far}")

    near, far, blind = scenario(patched, [], t1)
    check("T2.radius-off-everybody-gets-it", near == 1 and blind == 1 and far == 1, f"near={near} blind={blind} far={far}")

    def t3(S, NEAR, FAR, BLIND):
        S.door()
        return FAR.got(CH_DOOR, 4)

    far_door = scenario(patched, ["--trigger-radius", "1000"], t3)
    check("T3.doors-are-not-filtered", far_door == 1, f"far got {far_door} door packet(s)")

    near, far, blind = scenario(upstream, [], t1)
    check("T4.twin-upstream-relay-violates-the-T1-expectation", not (near == 1 and blind == 1 and far == 0),
          f"upstream: near={near} blind={blind} far={far} (far must receive it there)")

    def t5(S, NEAR, FAR, BLIND):
        BLIND.trigger()                      # sender without a known position
        return NEAR.got(CH_WORLD, 1), FAR.got(CH_WORLD, 1, 0.4)

    near, far = scenario(patched, ["--trigger-radius", "1000"], t5)
    check("T5.sender-without-position-fails-open", near == 1 and far == 1, f"near={near} far={far}")

    # Late join: a peer that joins while an enemy is alive asks for the enemy snapshot (WORLD_REQUEST_ENEMIES 0x0A)
    # and must get SPAWN (1) and the current position LOC (4, the id the 2.1.0 client sends).
    def late(exe):
        p = run_relay(exe, [])
        try:
            owner = Peer()
            owner.at(0)
            owner.enemy(1, "OLEnemyTest_0", bytes([8]) + b"OLEnemyX" + bytes(30))   # SPAWN
            owner.enemy(4, "OLEnemyTest_0", bytes(30))                              # LOC
            time.sleep(0.5)
            joiner = Peer()
            joiner.got_types(3, 0.3)
            joiner.send(CH_WORLD, 0x0A)                                              # REQUEST_ENEMIES
            return joiner.got_types(3, 1.0)
        finally:
            p.kill()
            time.sleep(0.5)

    seen = late(patched)
    check("T6.late-joiner-gets-enemy-spawn-and-position", {1, 4} <= seen, f"types received {sorted(seen)}")
    seen_up = late(upstream)
    check("T7.twin-upstream-relay-loses-the-enemy-position", 1 in seen_up and 4 not in seen_up, f"upstream types {sorted(seen_up)} (LOC 4 missing = the bug)")

    print(f"SUMMARY: {sum(results)}/{len(results)} -> {'PASS' if all(results) else 'FAIL'}", flush=True)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
