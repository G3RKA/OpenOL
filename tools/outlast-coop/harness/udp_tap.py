"""Logging UDP proxy between OpenOL clients and a relay, with a decoded state dump for bots.

  python -I udp_tap.py <listen_port> <relay_host> <relay_port> <log_file> [state_json]

Each client gets its own upstream socket, so the relay still sees one address per client.
Log: one line per interesting packet (time, direction, client port, channel, type, decoded fields).
Hero state, head rotation, ping and door angle snapshots are only counted / stored, not logged.
state_json (rewritten every 0.5 s): heroes by client port (x, y, z, yaw), doors by position
(last angle seen per direction), enemies by name (last position per sender).

Wire format (OpenOL 2.1.0, MultiplayerLink.cpp SendBinary): [channel][type][player_id LE4][payload].
"""
import json
import os
import select
import socket
import struct
import sys
import time

CH = {0: "SRV", 1: "HERO", 2: "DOOR", 3: "ENEMY", 4: "PUSH", 5: "WORLD"}
DOOR_T = {1: "LOCK", 2: "UNLOCK", 3: "STATE", 4: "OPEN", 5: "CLOSE", 6: "ANGLE", 7: "PARAMS",
          8: "DENY", 9: "INIT"}
WORLD_T = {1: "TRIGGER_ACT", 2: "ITEM_CONSUME", 3: "PICKUP_STATE", 4: "PICKUP_START", 5: "PICKUP_ATTACH",
           6: "PICKUP_KISMET", 7: "RECORDING", 8: "DISCONNECT", 9: "REQUEST_STATE", 0x0A: "REQUEST_ENEMIES",
           0x0B: "REQUEST_DOORS", 0x0C: "REQUEST_PUSHABLES", 0x0D: "MATINEE_STATE", 0x0E: "TRIGGER_FIRE",
           0x0F: "TRIGGER_DENIED", 0x10: "REQUEST_TRIGGERS"}
# Client PacketChannels.h ids (the relay's own ENEMY_* numbering differs).
ENEMY_T = {1: "SPAWN", 2: "DEL", 3: "SMT", 4: "LOC", 5: "DOOR_OPEN"}
QUIET = {("HERO", 0x01), ("HERO", 0x03), ("SRV", 0x02), ("DOOR", 0x06), ("DOOR", 0x09),
         ("ENEMY", 0x04)}

state = {"heroes": {}, "doors": {}, "enemies": {}}
events_out = None  # set in main(); decoded state changes go to the same log


def log_event(text):
    if events_out:
        events_out.write(f"{time.strftime('%H:%M:%S')} {text}\n")


def pid_of(data):
    return struct.unpack_from("<I", data, 2)[0] if len(data) >= 6 else -1


def decode(direction, client, data):
    """Returns (text, quiet) and updates `state`."""
    if not data:
        return "empty", True
    b0 = data[0]
    if b0 >= 0xE0:
        return f"SRVMSG 0x{b0:02x}", False
    if b0 == ord("H"):
        return "HELLO-text", False
    ch = CH.get(b0, f"ch{b0}")
    t = data[1] if len(data) > 1 else -1
    extra = ""
    if ch == "HERO" and t == 0x01 and len(data) >= 40 and direction == "C>R":
        # HeroChannel.cpp BuildStatePacket: X,Y,Z f32 @6; pitch,yaw u16 @18; vel i16x3 @22;
        # crouch,camcorder,specialmove,locomotion u8 @28; ladder,ledgehang,ledgewalk i16 @32; health i16 @38
        x, y, z = struct.unpack_from("<fff", data, 6)
        pitch, yaw = struct.unpack_from("<HH", data, 18)
        smove = data[30]
        hp = struct.unpack_from("<h", data, 38)[0]
        h = state["heroes"].get(str(client), {})
        if h and (h.get("hp") != hp or h.get("smove") != smove):
            log_event(f"C>R {client} HERO pid {pid_of(data)} hp {h.get('hp')}->{hp} smove {h.get('smove')}->{smove}"
                      f" at ({x:.0f},{y:.0f},{z:.0f})")
        state["heroes"][str(client)] = {"pid": pid_of(data), "x": round(x, 1), "y": round(y, 1),
                                        "z": round(z, 1), "yaw": yaw, "pitch": pitch, "hp": hp, "smove": smove,
                                        "t": time.time(), "raw": data.hex()}  # template for fake_peer
    elif ch == "HERO" and t == 0x08 and len(data) >= 7:
        extra = " LIFECYCLE " + {0: "DIED", 1: "RESPAWNED"}.get(data[6], str(data[6]))
    elif ch == "DOOR" and len(data) >= 18:
        x, y, z = struct.unpack_from("<iii", data, 6)
        key = f"{x},{y},{z}"
        d = state["doors"].setdefault(key, {})
        name = DOOR_T.get(t, f"0x{t:02x}")
        extra = f" {name} pos=({x},{y},{z})"
        if len(data) >= 22 and t in (3, 6, 9):
            ang = struct.unpack_from("<i", data, 18)[0]
            extra += f" angle={ang / 1000:.3f}"
            d[f"{direction} {client} angle"] = ang
            if t == 6 and direction == "C>R":
                return f"DOOR{extra} from pid {pid_of(data)}", False  # a client moved a door
        if t in (4, 5, 1, 2, 3):
            d.setdefault("events", []).append(f"{time.strftime('%H:%M:%S')} {direction} {client} {name}")
        return f"DOOR{extra}", (ch, t) in QUIET
    elif ch == "ENEMY" and len(data) > 7:
        n = data[6]
        ename = data[7:7 + n].decode("ascii", "replace")
        extra = f" {ENEMY_T.get(t, hex(t))} {ename}"
        if t == 4 and len(data) >= 7 + n + 1 + 19:
            # EnemyChannel.cpp: [name][0] X,Y,Z f32, yaw u16, velX,velY i16, EnemyMode u8
            o = 7 + n + 1
            x, y, z = struct.unpack_from("<fff", data, o)
            mode = data[o + 18]
            if len(data) >= o + 20 + 12:
                # EnvIdx u8, then BotLookAt (target's eye location) f32x3, look-active u8
                look = struct.unpack_from("<fff", data, o + 20)
                state["enemies"].setdefault(ename, {})[f"{direction} {client} look"] = [round(v) for v in look]
            e = state["enemies"].setdefault(ename, {})
            key = f"{direction} {client}"
            if e.get(key + " mode") not in (None, mode):
                log_event(f"{key} ENEMY {ename} mode {e.get(key + ' mode')}->{mode} at ({x:.0f},{y:.0f},{z:.0f})")
            e[key] = [round(x), round(y), round(z)]
            e[key + " mode"] = mode
            e[key + " t"] = time.time()
    elif ch == "PUSH" and t in (1, 3) and len(data) >= 27:
        # PushableChannelPackets.h FPushStatePacket: KeyX,Y,Z i32 @6, DispX1000 i32 @18, Seq u32 @22, bPushing u8 @26
        kx, ky, kz, disp, seq = struct.unpack_from("<iiiiI", data, 6)
        pushing = data[26]
        key = f"{kx},{ky},{kz}"
        o = state.setdefault("pushables", {}).setdefault(key, {})
        o[f"{direction} {client}"] = {"disp": disp / 1000.0, "pushing": pushing, "t": time.time()}
        return f"PUSH {'INIT' if t == 3 else 'STATE'} key=({kx},{ky},{kz}) disp={disp / 1000.0:.3f} pushing={pushing} seq={seq}", (t == 1 and pushing == 1 and seq > 1)
    elif ch == "WORLD":
        # PacketChannels.h WORLD_*; payload starts at 6
        name = WORLD_T.get(t, f"0x{t:02x}")
        p = data[6:]
        if t == 0x01 and len(p) >= 5:      # TRIGGER_ACT [count LE4][len][path]
            cnt, n = struct.unpack_from("<i", p, 0)[0], p[4]
            extra = f" {name} count={cnt} {p[5:5 + n].decode('utf-8', 'replace')}"
        elif t == 0x0E and len(p) >= 3:    # TRIGGER_FIRE [subtype][max][len][path]
            extra = f" {name} sub={p[0]} max={p[1]} {p[3:3 + p[2]].decode('utf-8', 'replace')}"
        elif t in (0x02, 0x06, 0x07, 0x0F) and len(p) >= 1:
            extra = f" {name} {p[1:1 + p[0]].decode('utf-8', 'replace')}"
        elif t == 0x0D and len(p) >= 1:    # MATINEE_STATE [count]{[len][path][pos f32][rate f32]}
            o, items = 1, []
            for _ in range(p[0]):
                if o >= len(p):
                    break
                n = p[o]; path = p[o + 1:o + 1 + n].decode("ascii", "replace"); o += 1 + n
                if o + 8 > len(p):
                    break
                pos, rate = struct.unpack_from("<ff", p, o); o += 8
                items.append((path, pos, rate))
            key = f"{direction} {client}"
            for path, pos, rate in items:
                m = state.setdefault("matinees", {}).setdefault(path.rsplit(".", 1)[-1], {})
                if key not in m or abs(m[key][1] - rate) > 0.01:
                    log_event(f"{key} MATINEE {path} pos={pos:.2f} rate={rate:.2f}")
                m[key] = [round(pos, 2), rate]
            return f"WORLD {name} n={len(items)}", True
        else:
            extra = f" {name}"
        return f"WORLD{extra}", False
    return f"{ch} 0x{t:02x}{extra}", (ch, t) in QUIET


def udp_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if hasattr(socket, "SIO_UDP_CONNRESET"):
        # Windows: a closed peer would otherwise make recvfrom raise WSAECONNRESET.
        s.ioctl(socket.SIO_UDP_CONNRESET, False)
    return s


def main():
    lport, rhost, rport, logf = int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4]
    statef = sys.argv[5] if len(sys.argv) > 5 else None
    relay = (rhost, rport)
    down = udp_socket()
    down.bind(("127.0.0.1", lport))   # loopback only: a 0.0.0.0 bind makes Windows Firewall ask the user for permission
    ups = {}       # client addr -> upstream socket
    owner = {}     # upstream socket -> client addr
    counts = {}
    out = open(logf, "a", buffering=1, encoding="utf-8")
    out.write(f"# tap {lport} -> {rhost}:{rport} started {time.strftime('%H:%M:%S')}\n")
    global events_out
    events_out = out
    last_summary = last_state = time.time()
    while True:
        r, _, _ = select.select([down] + list(owner), [], [], 0.5)
        for s in r:
            try:
                data, addr = s.recvfrom(65535)
            except OSError:
                continue
            if s is down:
                if addr not in ups:
                    u = udp_socket()
                    u.bind(("127.0.0.1", 0))
                    ups[addr], owner[u] = u, addr
                    out.write(f"{time.strftime('%H:%M:%S')} new client {addr[1]}\n")
                ups[addr].sendto(data, relay)
                direction, client = "C>R", addr[1]
            else:
                client_addr = owner[s]
                down.sendto(data, client_addr)
                direction, client = "R>C", client_addr[1]
            what, quiet = decode(direction, client, data)
            key = (direction, client, " ".join(what.split(" ")[:2]))
            counts[key] = counts.get(key, 0) + 1
            if not quiet:
                out.write(f"{time.strftime('%H:%M:%S')} {direction} {client} {what} len={len(data)}\n")
        now = time.time()
        if statef and now - last_state > 0.5:
            last_state = now
            tmp = statef + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f)
            try:
                os.replace(tmp, statef)
            except PermissionError:
                pass  # a reader has it open (Windows); next tick retries
        if now - last_summary > 60:
            last_summary = now
            out.write(f"{time.strftime('%H:%M:%S')} counts " +
                      ", ".join(f"{d} {c} {w}={n}" for (d, c, w), n in sorted(counts.items())) + "\n")


if __name__ == "__main__":
    main()
