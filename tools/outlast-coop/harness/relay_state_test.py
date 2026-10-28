"""Game-free protocol tests for the relay's shared-state handling: doors, pushables, late-join snapshots (about 30 s).

  python -I relay_state_test.py <relay.exe>

Uses fake peers (see relay_filter_test.Peer) on UDP 17791. Wire format: [channel][type][player_id LE4][payload].
Every check prints RESULT: PASS|FAIL <name>; the exit code is 0 only if all pass. These are upstream behaviours (the patched
and the upstream relay must both pass), so a regression in any relay build shows up here.

  S1  door lock is exclusive: a second player's DOOR_LOCK on the same door is answered with the server packet SRV_DOOR_DENY (0xE4), not relayed
  S2  after the owner unlocks, the other player can lock it (no deny)
  S3  DOOR_INIT is first-write-wins, never relayed, and a late joiner's REQUEST_DOORS gets the FIRST angle as DOOR_ANGLE (6)
  S4  a DOOR_OPEN is relayed live and a late joiner gets it as the door's state (4)
  S5  pushable ownership: a second player's PUSH_STATE with bPushing=1 on a pushed object gets PUSH_DENIED (2), the owner gets nothing
  S6  after the owner releases (bPushing=0) the other player can push it
  S7  PUSH_INIT is never relayed; a late joiner's REQUEST_PUSHABLES gets the first position as PUSH_STATE (1) with bPushing cleared
  S8  twin: a relay that relays everything blindly (a plain mirror) fails S1 (proves the checks can fail)
  S9  a PICKUP_STATE (item taken at X,Y,Z) is relayed live and replayed to a late joiner; a second PICKUP_STATE at the same place replaces it (one snapshot)
  S10 a PICKUP_KISMET (path name) is relayed live and replayed to a late joiner
  S11 a player's last HERO_STATE and last MATINEE_STATE are replayed to a late joiner (the last one, not the first)
  S12 after the owner of a hero/matinee snapshot leaves, a later joiner no longer gets that player's hero snapshot, but still gets the pickups (room state)
  S13 twin: the blind mirror gives a late joiner nothing, so S9's replay expectation fails on it
  S14 the exe patch's world packets 0x11 (shared checkpoint load) and 0x12 (enemy animation) are relayed unchanged, not echoed to the sender, not replayed to a late joiner
"""
import os
import socket
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import relay_filter_test as rf  # noqa: E402

CH_HERO, CH_DOOR, CH_PUSH, CH_WORLD = 1, 2, 4, 5
results = []


def check(name, ok, why=""):
    results.append(ok)
    print(f"RESULT: {'PASS' if ok else 'FAIL'} {name} {why}".rstrip(), flush=True)


def door_pkt(x, y, z, extra=b"\0" * 8):
    return struct.pack("<iii", x, y, z) + extra


def push_pkt(x, y, z, disp, seq, pushing):
    return struct.pack("<iiiiIB", x, y, z, disp, seq, pushing)


def recv_all(peer, window):
    """[(channel, type, payload)] received during `window` seconds."""
    end, out = time.time() + window, []
    while time.time() < end:
        try:
            d, _ = peer.s.recvfrom(65535)
        except socket.timeout:
            continue
        if len(d) >= 2:
            out.append((d[0], d[1], d[2:]))
    return out


def types(pkts, ch):
    return [t for c, t, _ in pkts if c == ch]


def with_relay(exe, fn):
    p = rf.run_relay(exe, [])
    try:
        return fn()
    finally:
        p.kill()
        time.sleep(0.5)


def doors():
    P1, P2 = rf.Peer(), rf.Peer()
    recv_all(P1, 0.3), recv_all(P2, 0.3)
    k = (100, 200, 300)
    P1.send(CH_DOOR, 1, door_pkt(*k))                       # DOOR_LOCK by P1
    time.sleep(0.2)
    recv_all(P2, 0.3)
    P2.send(CH_DOOR, 1, door_pkt(*k))                       # DOOR_LOCK by P2 -> deny
    got2 = recv_all(P2, 0.6)
    got1 = recv_all(P1, 0.3)
    # the relay answers with a server packet SRV_DOOR_DENY (0xE4) carrying the door key; the lock itself is not relayed
    denied = any(c == 0xE4 for c, _, _ in got2)
    check("S1.door-lock-is-exclusive", denied and 1 not in types(got1, CH_DOOR),
          f"P2 got deny {denied}, P2 door types {types(got2, CH_DOOR)}, P1 got {types(got1, CH_DOOR)}")
    P1.send(CH_DOOR, 2, door_pkt(*k))                       # DOOR_UNLOCK by the owner
    time.sleep(0.2)
    recv_all(P2, 0.3)
    P2.send(CH_DOOR, 1, door_pkt(*k))
    got2 = recv_all(P2, 0.6)
    check("S2.other-player-can-lock-after-unlock", not any(c == 0xE4 for c, _, _ in got2), f"P2 got {[(c, t) for c, t, _ in got2]}")


def door_snapshots():
    P1, P2 = rf.Peer(), rf.Peer()
    recv_all(P1, 0.3), recv_all(P2, 0.3)
    k = (500, 600, 700)
    P1.send(CH_DOOR, 9, door_pkt(*k, extra=struct.pack("<i", 11000)))   # DOOR_INIT angle 11.000
    P2.send(CH_DOOR, 9, door_pkt(*k, extra=struct.pack("<i", 99000)))   # second INIT must be ignored
    time.sleep(0.3)
    relayed = types(recv_all(P1, 0.4), CH_DOOR) + types(recv_all(P2, 0.4), CH_DOOR)
    P3 = rf.Peer()
    recv_all(P3, 0.3)
    P3.send(CH_WORLD, 0x0B)                                  # REQUEST_DOORS
    snap = [(t, p) for c, t, p in recv_all(P3, 0.8) if c == CH_DOOR]
    angles = [struct.unpack_from("<i", p, 4 + 12)[0] for t, p in snap if t == 6 and len(p) >= 20]
    check("S3.door-init-first-write-wins-never-relayed", not relayed and angles == [11000],
          f"relayed {relayed}, replayed angles {angles}")
    P1.send(CH_DOOR, 4, door_pkt(900, 901, 902, extra=b""))   # DOOR_OPEN live
    live = types(recv_all(P2, 0.6), CH_DOOR)
    P4 = rf.Peer()
    recv_all(P4, 0.3)
    P4.send(CH_WORLD, 0x0B)
    late = types(recv_all(P4, 0.8), CH_DOOR)
    check("S4.door-open-live-and-in-late-join-snapshot", 4 in live and 4 in late, f"live {live}, late {late}")


def pushables():
    P1, P2 = rf.Peer(), rf.Peer()
    recv_all(P1, 0.3), recv_all(P2, 0.3)
    k = (10, 20, 30)
    P1.send(CH_PUSH, 1, push_pkt(*k, 500, 1, 1))              # P1 starts pushing
    seen_by_2 = types(recv_all(P2, 0.5), CH_PUSH)
    P2.send(CH_PUSH, 1, push_pkt(*k, 600, 1, 1))              # P2 tries too
    got2 = types(recv_all(P2, 0.5), CH_PUSH)
    got1 = types(recv_all(P1, 0.3), CH_PUSH)
    check("S5.push-ownership-second-pusher-denied", 1 in seen_by_2 and 2 in got2 and not got1,
          f"P2 saw {seen_by_2}, P2 got {got2}, P1 got {got1}")
    P1.send(CH_PUSH, 1, push_pkt(*k, 700, 2, 0))              # P1 releases
    time.sleep(0.2)
    recv_all(P2, 0.3)
    P2.send(CH_PUSH, 1, push_pkt(*k, 800, 2, 1))
    got2 = types(recv_all(P2, 0.5), CH_PUSH)
    check("S6.pusher-allowed-after-release", 2 not in got2, f"P2 got {got2}")


def push_snapshots():
    P1, P2 = rf.Peer(), rf.Peer()
    recv_all(P1, 0.3), recv_all(P2, 0.3)
    k = (40, 50, 60)
    P1.send(CH_PUSH, 3, push_pkt(*k, 111, 0, 0))              # PUSH_INIT first
    P2.send(CH_PUSH, 3, push_pkt(*k, 999, 0, 0))              # second INIT ignored
    time.sleep(0.3)
    relayed = types(recv_all(P1, 0.4), CH_PUSH) + types(recv_all(P2, 0.4), CH_PUSH)
    P3 = rf.Peer()
    recv_all(P3, 0.3)
    P3.send(CH_WORLD, 0x0C)                                    # REQUEST_PUSHABLES
    snap = [(t, p) for c, t, p in recv_all(P3, 0.8) if c == CH_PUSH]
    disps = [struct.unpack_from("<i", p, 4 + 12)[0] for t, p in snap if t == 1 and len(p) >= 25]
    pushing = [p[4 + 20] for t, p in snap if t == 1 and len(p) >= 25]
    check("S7.push-init-first-write-wins-never-relayed-bpushing-cleared", not relayed and disps == [111] and pushing == [0],
          f"relayed {relayed}, replayed disp {disps}, bPushing {pushing}")


def mirror_twin():
    """A blind mirror 'relay' (echoes every packet to the other peers, no ownership) must fail S1."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", rf.PORT))
    s.settimeout(0.2)
    peers = {}
    stop = time.time() + 6

    def serve():
        while time.time() < stop:
            try:
                d, a = s.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                continue
            if d.startswith(b"HELLO"):
                peers[a] = len(peers) + 1000
                ready = bytes([0xE0]) + bytes(4) + struct.pack("<I", peers[a]) + bytes([1, 88])
                s.sendto(ready, a)
                continue
            for b in peers:
                if b != a:
                    s.sendto(d, b)
    import threading
    threading.Thread(target=serve, daemon=True).start()
    try:
        P1, P2 = rf.Peer(), rf.Peer()
        recv_all(P1, 0.3), recv_all(P2, 0.3)
        k = (100, 200, 300)
        P1.send(CH_DOOR, 1, door_pkt(*k))
        recv_all(P2, 0.3)
        P2.send(CH_DOOR, 1, door_pkt(*k))
        got2 = recv_all(P2, 0.5)
        got1 = recv_all(P1, 0.3)
        s1_would_pass = any(c == 0xE4 for c, _, _ in got2) and 1 not in types(got1, CH_DOOR)
        check("S8.twin-a-blind-mirror-fails-the-S1-expectation", not s1_would_pass,
              f"mirror: P2 got {[(c, t) for c, t, _ in got2]}, P1 got door types {types(got1, CH_DOOR)}")
    finally:
        stop = 0
        time.sleep(0.4)
        s.close()


def pickups():
    P1, P2 = rf.Peer(), rf.Peer()
    recv_all(P1, 0.3), recv_all(P2, 0.3)
    pos = struct.pack("<iii", 7, 8, 9)
    P1.send(CH_WORLD, 3, pos + b"")                      # PICKUP_STATE (taken)
    live = [t for c, t, _ in recv_all(P2, 0.5) if c == CH_WORLD]
    P1.send(CH_WORLD, 3, pos + b"")                      # same place again: replaces the snapshot
    path = b"lvl.TheWorld:PersistentLevel.Pickup_Battery_4"
    P1.send(CH_WORLD, 6, bytes([len(path)]) + path)            # PICKUP_KISMET
    live_k = [t for c, t, _ in recv_all(P2, 0.5) if c == CH_WORLD]
    check("S9a.pickup-state-relayed-live", 3 in live, f"P2 saw world types {live}")
    check("S10a.pickup-kismet-relayed-live", 6 in live_k, f"P2 saw world types {live_k}")
    P3 = rf.Peer()
    got = [(t, p) for c, t, p in recv_all(P3, 1.5) if c == CH_WORLD]
    states = [p for t, p in got if t == 3]
    kismet = [p for t, p in got if t == 6]
    check("S9.pickup-state-replayed-once-latest-wins", len(states) == 1 and states[0][4:16] == pos and states[0][16:17] == b"",
          f"replayed {len(states)} state packets, payload tail {[p[16:17] for p in states]}")
    check("S10.pickup-kismet-replayed", len(kismet) == 1 and kismet[0][5:] == path, f"replayed {len(kismet)}")
    return P1, P2, P3


def patch_world_types():
    """The exe patch's own world packets (0x11 shared checkpoint load, 0x12 enemy animation) are unknown to the relay: it must relay them unchanged
    to the other player, must not echo them to the sender and must not replay them to a late joiner (they are events, not state)."""
    P1, P2 = rf.Peer(), rf.Peer()
    recv_all(P1, 0.3), recv_all(P2, 0.3)
    name, anim = b"OLEnemyPatient_3", b"Idle_LeanWall"
    ev = {0x11: bytes([len(b"Admin_MainHall")]) + b"Admin_MainHall" + bytes([len(b"AdminBlock_Persistent")]) + b"AdminBlock_Persistent",
          0x12: bytes([len(name)]) + name + bytes([len(anim)]) + anim + b"\x01" + struct.pack("<fffff", 1.0, 0.2, 0.2, 0.0, 0.0)}
    for t, payload in ev.items():
        P1.send(CH_WORLD, t, payload)
    got2 = {t: p for c, t, p in recv_all(P2, 0.8) if c == CH_WORLD and t in ev}
    got1 = [t for c, t, _ in recv_all(P1, 0.3) if c == CH_WORLD and t in ev]
    # the relay puts the sender's id after the type byte ([channel][type][player_id LE4][payload]); the payload must be unchanged
    same = {t: len(p) >= 4 + len(ev[t]) and p[4:4 + len(ev[t])] == ev[t] for t, p in got2.items()}
    check("S14.exe-patch-world-types-relayed-unchanged", set(got2) == set(ev) and all(same.values()), f"P2 got {sorted(got2)}, payload equal {same}")
    check("S14b.exe-patch-world-types-not-echoed-to-the-sender", not got1, f"P1 got {got1}")
    P3 = rf.Peer()
    late = [t for c, t, _ in recv_all(P3, 1.2) if c == CH_WORLD and t in ev]
    check("S14c.exe-patch-world-types-not-replayed-to-a-late-joiner", not late, f"late joiner got {late}")


def player_snapshots():
    P1, P2 = rf.Peer(), rf.Peer()
    recv_all(P1, 0.3), recv_all(P2, 0.3)
    P1.send(CH_HERO, 1, struct.pack("<fff", 1.0, 0.0, 0.0) + bytes(30))
    P1.send(CH_HERO, 1, struct.pack("<fff", 2.0, 0.0, 0.0) + bytes(30))   # the later one must win
    P1.send(CH_WORLD, 0x0D, b"matinee-first")
    P1.send(CH_WORLD, 0x0D, b"matinee-second")
    time.sleep(0.3)
    recv_all(P2, 0.3)
    P3 = rf.Peer()
    got = [(c, t, p) for c, t, p in recv_all(P3, 1.5)]
    heroes = [struct.unpack_from("<f", p, 4)[0] for c, t, p in got if c == CH_HERO and t == 1 and len(p) >= 8]
    mats = [p[4:] for c, t, p in got if c == CH_WORLD and t == 0x0D]
    check("S11.late-joiner-gets-latest-hero-and-matinee-state", heroes == [2.0] and mats == [b"matinee-second"],
          f"hero x {heroes}, matinee {mats}")
    P1.send(5, 8)                                              # WORLD_DISCONNECT: P1 leaves
    time.sleep(0.5)
    recv_all(P2, 0.3), recv_all(P3, 0.3)
    P4 = rf.Peer()
    got = recv_all(P4, 1.5)
    heroes = [struct.unpack_from("<f", p, 4)[0] for c, t, p in got if c == CH_HERO and t == 1 and len(p) >= 8]
    check("S12.snapshot-of-a-player-who-left-is-gone", 2.0 not in heroes, f"hero x seen by the next joiner {heroes}")


def mirror_join_twin():
    """The blind mirror forgets everything: a late joiner gets no pickup replay, so S9's expectation fails (S14)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", rf.PORT))
    s.settimeout(0.2)
    peers = {}
    stop = time.time() + 6

    def serve():
        while time.time() < stop:
            try:
                d, a = s.recvfrom(65535)
            except (socket.timeout, OSError):
                continue
            if d.startswith(b"HELLO"):
                peers[a] = len(peers) + 1000
                s.sendto(bytes([0xE0]) + bytes(4) + struct.pack("<I", peers[a]) + bytes([1, 88]), a)
                continue
            for b in peers:
                if b != a:
                    s.sendto(d, b)
    import threading
    threading.Thread(target=serve, daemon=True).start()
    try:
        P1 = rf.Peer()
        recv_all(P1, 0.3)
        P1.send(CH_WORLD, 3, struct.pack("<iii", 7, 8, 9) + b"")
        P3 = rf.Peer()
        got = [x for x in recv_all(P3, 1.0) if x[0] == CH_WORLD and x[1] == 3]
        check("S13.twin-blind-mirror-has-no-late-join-replay", not got, f"mirror replayed {len(got)} pickup packets to the joiner")
    finally:
        stop = 0
        time.sleep(0.4)
        s.close()


def main():
    exe = sys.argv[1]
    with_relay(exe, doors)
    with_relay(exe, door_snapshots)
    with_relay(exe, pushables)
    with_relay(exe, push_snapshots)
    mirror_twin()
    with_relay(exe, pickups)
    with_relay(exe, patch_world_types)
    with_relay(exe, player_snapshots)
    mirror_join_twin()
    print(f"SUMMARY: {sum(results)}/{len(results)} -> {'PASS' if all(results) else 'FAIL'}", flush=True)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
