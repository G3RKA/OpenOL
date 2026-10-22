"""Walk a game client's hero to a point using the tap's decoded state (real input, needs focus).

  python -I goto.py <window_pid> <client_port> <x> <y> [stop_dist=90] [state=state.json]

Reads hero x/y/yaw from udp_tap.py's state file, turns with relative mouse moves
(counts-per-yaw-unit calibrated on the first turn), walks with W in short bursts.
UE3 yaw: 65536 units = 360 degrees, yaw 0 = +X, 16384 = +Y.
"""
import ctypes
import json
import math
import subprocess
import sys
import time

u = ctypes.windll.user32
here = __file__.rsplit("\\", 1)[0] if "\\" in __file__ else "."


def hero(port, statef):
    for _ in range(10):
        try:
            with open(statef, encoding="utf-8") as f:
                return json.load(f)["heroes"][str(port)]
        except (OSError, ValueError):
            time.sleep(0.05)  # tap is replacing the file
    raise SystemExit("state file unreadable")


def fresh(port, statef, after):
    for _ in range(12):
        h = hero(port, statef)
        if h["t"] > after + 0.3:
            return h
        time.sleep(0.25)
    raise SystemExit(f"STALE: no hero update for client {port} in 3 s (tap or client down?)")


def mouse_dx(dx):
    steps = max(1, abs(int(dx)) // 30)
    for i in range(steps):
        u.mouse_event(1, int(dx / steps), 0, 0, 0)
        time.sleep(0.01)


def hold_w(sec):
    u.keybd_event(0x57, 0x11, 0, 0)
    time.sleep(sec)
    u.keybd_event(0x57, 0x11, 2, 0)


def yaw_err(target, yaw):
    return ((target - yaw + 32768) % 65536) - 32768


def main():
    wpid, port, tx, ty = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
    stop = float(sys.argv[5]) if len(sys.argv) > 5 else 90
    statef = sys.argv[6] if len(sys.argv) > 6 else "state.json"
    subprocess.run([sys.executable, "-I", f"{here}\\olwin.py", "focus", str(wpid)], capture_output=True)
    time.sleep(0.5)
    # Calibrate: yaw units per mouse count.
    h0 = fresh(port, statef, time.time())
    t = time.time()
    mouse_dx(300)
    h1 = fresh(port, statef, t)
    k = yaw_err(h1["yaw"], h0["yaw"]) / 300 or 50.0
    print(f"calib: {k:.2f} yaw units per mouse count", flush=True)
    stuck = 0                # bursts in a row without getting closer than `best`
    best = float("inf")      # closest distance to the target so far
    for step in range(80):
        h = fresh(port, statef, time.time())
        dist = math.hypot(tx - h["x"], ty - h["y"])
        want = int(math.degrees(math.atan2(ty - h["y"], tx - h["x"])) / 360 * 65536) % 65536
        err = yaw_err(want, h["yaw"])
        print(f"step {step}: pos=({h['x']:.0f},{h['y']:.0f}) yaw={h['yaw']} dist={dist:.0f} err={err}", flush=True)
        if dist <= stop:
            print("arrived", flush=True)
            return 0
        if abs(err) > 600:
            mouse_dx(err / k)
            time.sleep(0.2)
            continue
        # Short bursts, so a wall or the other player is noticed after at most ~0.6 s of walking.
        sec = min(0.6, max(0.25, dist / 300))
        t = time.time()
        hold_w(sec)
        h2 = fresh(port, statef, t + sec)
        if h2.get("smove") or (h2.get("hp") or 0) < (h.get("hp") or 0):
            # Grabbed / thrown / hit: not an obstacle. Stop and let the caller decide.
            print(f"HIT: hp {h.get('hp')}->{h2.get('hp')} special move {h2.get('smove')}"
                  f" at ({h2['x']:.0f},{h2['y']:.0f})", flush=True)
            return 3
        d2 = math.hypot(tx - h2["x"], ty - h2["y"])
        # Progress = a new best distance. Sliding along furniture or bouncing back and forth
        # (moving, but not getting closer) counts as stuck too.
        if d2 < best - 30:
            best, stuck = d2, 0
            continue
        stuck += 1
        if stuck < 2:
            continue  # one bad burst can be a turn or a bump; act on the second
        n = stuck - 1  # 1, 2, 3, ... escalating detours
        if n > 6:
            print(f"BLOCKED: no progress after {n} detours at ({h2['x']:.0f},{h2['y']:.0f}),"
                  f" {d2:.0f} from target (best {best:.0f})", flush=True)
            return 2
        right = n % 2 == 1
        side = (0x44, 0x20) if right else (0x41, 0x1E)  # D, A
        print(f"  STUCK #{n} at ({h2['x']:.0f},{h2['y']:.0f}) dist {d2:.0f} best {best:.0f}:"
              f" back off, sidestep {'right' if right else 'left'} {0.4 * n:.1f}s, walk past", flush=True)
        u.keybd_event(0x53, 0x1F, 0, 0); time.sleep(0.25 + 0.1 * n); u.keybd_event(0x53, 0x1F, 2, 0)  # S
        u.keybd_event(side[0], side[1], 0, 0); time.sleep(0.4 * n)
        u.keybd_event(side[0], side[1], 2, 0)
        hold_w(0.5)  # step forward past the obstacle's edge before re-aiming
    print("gave up", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
