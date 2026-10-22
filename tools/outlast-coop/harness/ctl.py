"""Drive the registered game clients with real input, all in lockstep, and look at client A. Used for the natural-progress test.

  python -I ctl.py [-c 0|1|both] <op> ... [shot=name]

ops:  w|a|s|d <sec>        walk (W forward, A left, S back, D right)
      run <sec>            walk forward holding Shift
      look <dx> <dy>       relative mouse move (positive dx = turn right, positive dy = look down)
      key <hex>            tap a virtual key, e.g. 20 = Space, 0D = Enter, 1B = Esc, 45 = E, 43 = C
      hold <hex> <sec>     hold a key
      lmb <sec>            hold the left mouse button (interact)
      rmb <sec>            hold the right mouse button
      yaw <0..65535>       turn to an absolute yaw (0 = +X, 16384 = +Y, 32768 = -X, 49152 = -Y)
      wait <sec>
Prints the hero positions from state.json afterwards; shot=<name> saves a window-only picture of every driven client to scratch_dbg/NAME_IDX.png.
"""
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol

u = ol.u
SC = {0x57: 0x11, 0x41: 0x1E, 0x53: 0x1F, 0x44: 0x20, 0x10: 0x2A, 0x20: 0x39, 0x45: 0x12, 0x43: 0x2E, 0x51: 0x10, 0x46: 0x21, 0x11: 0x1D}
OUT = os.path.join(os.path.dirname(HERE), "scratch_dbg")


def kd(vk, up=False):
    u.keybd_event(vk, SC.get(vk, 0), 2 if up else 0, 0)


def look(dx, dy):
    n = max(abs(dx), abs(dy)) // 25 + 1
    for _ in range(n):
        u.mouse_event(1, int(dx / n), int(dy / n), 0, 0)
        time.sleep(0.01)


def hold(vks, sec):
    for vk in vks:
        kd(vk)
    time.sleep(sec)
    for vk in reversed(vks):
        kd(vk, True)


def face(c, target, tries=8):
    """Turn to an absolute yaw (65536 = 360 deg, 0 = +X, 16384 = +Y), closed loop on the yaw the proxy decodes."""
    for _ in range(tries):
        h = ol.read_state()["heroes"].get(str(c["port"]))
        err = ((target - h["yaw"] + 32768) % 65536) - 32768
        if abs(err) < 600:
            return
        look(int(err / 41.7), 0)
        time.sleep(0.5)


def zto(c, target, tries=5):
    """Ghost mode only: climb or dive to a height by flying a short way along a 45 degree view, then level the camera again."""
    for _ in range(tries):
        h = ol.read_state()["heroes"].get(str(c["port"]))
        dz = target - h["z"]
        if abs(dz) < 70:
            return
        ol.level_view(c["idx"])
        look(0, -400 if dz > 0 else 400)
        time.sleep(0.3)
        hold([0x57], min(1.5, abs(dz) / 480.0))
        ol.level_view(c["idx"])


def apply(op, a, c=None):
    if op in ("w", "a", "s", "d"):
        hold([ord(op.upper())], float(a[0]))
    elif op == "run":
        hold([0x10, 0x57], float(a[0]))
    elif op == "look":
        look(int(a[0]), int(a[1]))
    elif op == "key":
        ol.olwin.tap(int(a[0], 16))
    elif op == "hold":
        hold([int(a[0], 16)], float(a[1]))
    elif op in ("lmb", "rmb"):
        d, up = (2, 4) if op == "lmb" else (8, 16)
        u.mouse_event(d, 0, 0, 0, 0)
        time.sleep(float(a[0]))
        u.mouse_event(up, 0, 0, 0, 0)
    elif op == "zto":
        zto(c, int(a[0]))
    elif op == "level":
        ol.level_view(c["idx"])
    elif op == "yaw":
        face(c, int(a[0]))
    elif op == "wait":
        time.sleep(float(a[0]))
    else:
        raise SystemExit(f"unknown op {op}")


NARGS = {"w": 1, "a": 1, "s": 1, "d": 1, "run": 1, "look": 2, "key": 1, "hold": 2, "lmb": 1, "rmb": 1, "wait": 1, "yaw": 1, "level": 0, "zto": 1}


def shot(c, name):
    hwnd, r = ol.window_rect(c["pid"])
    ps = ("Add-Type -AssemblyName System.Drawing;"
          f"$b=New-Object System.Drawing.Bitmap {r[2]},{r[3]};$g=[System.Drawing.Graphics]::FromImage($b);"
          f"$g.CopyFromScreen({r[0]},{r[1]},0,0,$b.Size);$b.Save('{os.path.join(OUT, name)}.png')")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


def main():
    args = sys.argv[1:]
    which = "both"
    if args and args[0] == "-c":
        which, args = args[1], args[2:]
    name = None
    ops = []
    i = 0
    while i < len(args):
        if args[i].startswith("shot="):
            name = args[i][5:]
            i += 1
            continue
        n = NARGS[args[i]]
        ops.append((args[i], args[i + 1:i + 1 + n]))
        i += 1 + n
    cl = ol.clients()
    sel = cl if which == "both" else [cl[int(which)]]
    for c in sel:
        for _ in range(8):
            if ol.olwin.focus(c["hwnd"]):
                break
            time.sleep(0.5)
        time.sleep(0.3)
        for op, a in ops:
            apply(op, a, c)
        if name:
            time.sleep(0.5)
            shot(c, f"{name}_{c['idx']}")
    s = ol.read_state()
    print({c["idx"]: (round(s["heroes"][str(c["port"])]["x"]), round(s["heroes"][str(c["port"])]["y"]), round(s["heroes"][str(c["port"])]["z"]),
                      s["heroes"][str(c["port"])]["yaw"], s["heroes"][str(c["port"])]["hp"]) for c in cl if str(c["port"]) in s["heroes"]},
          "enemies:", {k: len(v) if hasattr(v, "__len__") else v for k, v in s["enemies"].items()})


if __name__ == "__main__":
    main()
