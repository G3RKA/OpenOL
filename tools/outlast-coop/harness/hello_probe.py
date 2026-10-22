"""Sends the same HELLO the OpenOL client sends (MultiplayerLink.cpp:
"HELLO,<room>,<password>\n") and decodes the relay's binary reply
(ServerPackets.h: 0xE0 READY, 0xE2 HELLO_FAIL; header [type][pad LE4]).

Usage: python -I hello_probe.py <host> <port> <room> [<room> ...]
Exit code 0 if every room listed after --expect-ok got READY and every
other room got the expected outcome printed; see main() for assertions.
"""
import socket
import sys

READY, ONLINE_COUNT, HELLO_FAIL = 0xE0, 0xE1, 0xE2


def probe(host, port, room, password=""):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2.0)
    s.sendto(f"HELLO,{room},{password}\n".encode("ascii"), (host, port))
    try:
        while True:
            data, _ = s.recvfrom(2048)
            t = data[0]
            if t == READY:
                pid = int.from_bytes(data[5:9], "little")
                name = data[10:10 + data[9]].decode("ascii", "replace")
                return ("READY", f"player_id={pid} server={name}")
            if t == HELLO_FAIL:
                return ("HELLO_FAIL", data[6:6 + data[5]].decode("ascii", "replace"))
            if t == ONLINE_COUNT:
                continue
            return ("OTHER", data[:16].hex())
    except socket.timeout:
        return ("TIMEOUT", "")
    finally:
        s.close()


def main():
    host, port = sys.argv[1], int(sys.argv[2])
    expect = {}
    for arg in sys.argv[3:]:
        room, _, want = arg.partition("=")
        expect[room] = want or None
    failed = 0
    for room, want in expect.items():
        kind, detail = probe(host, port, room)
        ok = want is None or kind == want
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'} room={room!r}: {kind} {detail} (expected {want})")
    print(f"{len(expect) - failed}/{len(expect)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
