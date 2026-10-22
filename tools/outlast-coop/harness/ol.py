"""One-command scenario driver for OpenOL co-op tests (replaces menu clicking and walking).

  python -I ol.py launch <n> [map]          start n clients straight on a map (default prison_persistent),
                                            wake them, tile the windows, learn each client's proxy port
  python -I ol.py cp <idx> <checkpoint>     load a checkpoint on client idx (0-based) via the F6 overlay search
  python -I ol.py cpall <checkpoint>        same on every client, one after the other
  python -I ol.py survey <idx> <cp> [cp...] load each checkpoint on client idx, print where the hero
                                            spawns and which enemies the client reports (name, distance)
  python -I ol.py maxhp <idx> <n>           set Max Health via the overlay slider
  python -I ol.py spawn <idx>               spawn a Soldier in front of the hero (overlay Spawns tab)
  python -I ol.py status                    clients, ports, hero position/hp, enemies per owner
  python -I ol.py up                        start relay + logging proxy (detached) and probe them
  python -I ol.py down                      stop clients, relay and proxy

State is kept in clients.json next to this file. Needs the relay and `udp_tap.py ... state.json`
running (the proxy on 17778 is what the clients' OLMultiplayer.ini points at).
Clients are started with -nosteam -FORCELOGFLUSH. Loads use real input into the foreground window.
"""
import ctypes
import ctypes.wintypes
import json
import math
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import olwin  # noqa: E402

GAME = os.environ.get("OL_GAME_DIR", r"<test copy>\Binaries\Win64")   # OpenOL-patched COPY of the game, never the real install
LOGS = os.environ.get("OL_LOG_DIR", r"<test copy>\OLGame\Logs")
STATE = os.path.join(HERE, "state.json")
TAPLOG = os.path.join(HERE, "tap.log")
REG = os.path.join(HERE, "clients.json")
u = ctypes.windll.user32


STACK = os.path.join(HERE, "stack.json")


def tap_log():
    if os.path.exists(STACK):
        return json.load(open(STACK))["tap_log"]
    return os.environ.get("OL_TAPLOG", TAPLOG)


def up(relay=True, target_port=17777, chaos=None):
    """Start relay (17777) and logging proxy (17778) detached; checks them with a HELLO probe.
    relay=False: only the proxy, pointing at target_port (for a relay that a game client starts itself, see embedded_relay).
    chaos="bad_wifi" (any profile of tools/chaos/profiles.json): a chaos relay (impairment: delay, loss, reorder) is put between the proxy and the relay; see chaos_call."""
    down(stack_only=True)
    stamp = time.strftime("%H%M%S")
    tl = os.path.join(HERE, f"tap_{stamp}.log")
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    if relay:
        subprocess.Popen([os.environ.get("OL_RELAY_EXE", os.path.join(HERE, "OpenOL_Relay.exe")), "--port", "17777", "--ip", "127.0.0.1", "--name", "CoopTest", *os.environ.get("OL_RELAY_ARGS", "").split()],
                         cwd=os.path.dirname(os.environ.get("OL_RELAY_EXE", os.path.join(HERE, "OpenOL_Relay.exe"))), creationflags=flags, stdin=subprocess.DEVNULL,
                         stdout=open(os.path.join(HERE, f"relay_{stamp}.log"), "w"), stderr=subprocess.STDOUT)
    if chaos:
        subprocess.Popen([sys.executable, "-I", chaos_script(), "relay", "--target", f"127.0.0.1:{target_port}", "--listen", "17779",
                          "--rpc-port", "17789", "--profile", chaos], creationflags=flags, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        target_port = 17779
        time.sleep(1)
    if os.path.exists(STATE):
        os.remove(STATE)
    subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "udp_tap.py"), "17778", "127.0.0.1", str(target_port), tl, STATE],
                     creationflags=flags, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    wait_firewall(what="relay / proxy")
    if relay:
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "hello_probe.py"), "127.0.0.1", "17778", "PUBLIC=READY"],
                           capture_output=True, text=True)
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "probe failed: " + r.stderr[-200:])
    json.dump({"tap_log": tl}, open(STACK, "w"))
    save([])
    print("stack up, proxy log", tl)


FIREWALL_TITLES = ("Security Alert", "безопасности Windows", "Брандмауэр", "Firewall")


def firewall_prompt():
    """Titles of visible Windows Firewall permission prompts ('Windows Security Alert'). They appear when a new program listens on a
    non-loopback address; they need the OWNER's click (changing security settings is not something a test script may do)."""
    found = []
    P = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

    def cb(h, _):
        if u.IsWindowVisible(h):
            t = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(h, t, 256)
            if any(k in t.value for k in FIREWALL_TITLES):
                found.append(t.value)
        return True

    u.EnumWindows(P(cb), 0)
    return found


def wait_firewall(timeout=240, what=""):
    """If a firewall prompt is open, say so once and wait (up to `timeout` s) until the owner has answered it; never clicks it."""
    if not firewall_prompt():
        return False
    print(f"WAITING for the owner: Windows Firewall asks for permission{' (' + what + ')' if what else ''}; click Allow, the run continues by itself", flush=True)
    t0 = time.time()
    while firewall_prompt() and time.time() - t0 < timeout:
        time.sleep(2)
    print("firewall prompt closed" if not firewall_prompt() else "firewall prompt still open after the timeout", flush=True)
    return True


def chaos_script():
    """tools/chaos/chaos.py of the coop-anything checkout (env OL_CHAOS overrides)."""
    for cand in (os.environ.get("OL_CHAOS"),
                 os.path.normpath(os.path.join(HERE, "..", "..", "..", "tools", "chaos", "chaos.py")),
                 os.path.normpath(os.path.join(HERE, "..", "coop-anything", "tools", "chaos", "chaos.py"))):
        if cand and os.path.exists(cand):
            return cand
    sys.exit("tools/chaos/chaos.py not found (set OL_CHAOS)")


def chaos_call(method, params="{}"):
    """JSON-RPC to the running chaos relay, e.g. chaos_call('disconnect', '{"duration_ms": 10000}')."""
    r = subprocess.run([sys.executable, "-I", chaos_script(), "call", "--rpc-port", "17789", method, params], capture_output=True, text=True, timeout=30)
    return r.stdout.strip()


def clients():
    return json.load(open(REG)) if os.path.exists(REG) else []


def save(c):
    json.dump(c, open(REG, "w"), indent=1)


def read_state():
    for _ in range(10):
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(0.05)
    sys.exit("state.json unreadable (is udp_tap.py running?)")


def n_tap_clients():
    try:
        return sum(1 for l in open(tap_log(), encoding="utf-8", errors="replace") if "new client" in l)
    except OSError:
        return 0


def type_text(text):
    for ch in text:
        for fl in (olwin.KEYEVENTF_UNICODE, olwin.KEYEVENTF_UNICODE | olwin.KEYEVENTF_KEYUP):
            inp = olwin.INPUT(type=1, ki=olwin.KEYBDINPUT(0, ord(ch), fl, 0, None))
            u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(olwin.INPUT))
        time.sleep(0.03)


def click(x, y):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.2)
    u.mouse_event(2, 0, 0, 0, 0)
    time.sleep(0.08)
    u.mouse_event(4, 0, 0, 0, 0)
    time.sleep(0.4)


def window_rect(pid):
    w = max(olwin.windows(pid), key=lambda w: w["rect"][2] * w["rect"][3])
    return w["hwnd"], w["rect"]


def launch(n, mapname, append=False):
    """Start n clients straight on a map. append=True keeps the clients already registered (a late joiner); the new ones get the next indexes."""
    reg = clients() if append else []
    first = len(reg)
    for i in range(first, first + n):
        before = n_tap_clients()
        log = f"mp_{chr(97 + i)}.log"
        pid = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Start-Process -FilePath '{GAME}\\OLGame.exe' -WorkingDirectory '{GAME}' -PassThru "
             f"-ArgumentList '{mapname}?game=Multiplayer.MultiplayerGame','-nostartupmovies','-nosteam',"
             f"'-FORCELOGFLUSH','-log={log}').Id"],
            capture_output=True, text=True).stdout.strip()
        pid = int(pid)
        print(f"client {i}: pid {pid}, log {log}", flush=True)
        # Engine init blocks right after the Wwise line until the window is minimized and restored;
        # waking earlier does nothing, so wait for that line and retry the wake until the proxy sees the client.
        logp = os.path.join(LOGS, log)
        for _ in range(90):
            try:
                if "Wwise(R) SDK Version" in open(logp, encoding="utf-8", errors="replace").read():
                    break
            except OSError:
                pass
            time.sleep(1)
        for attempt in range(4):
            subprocess.run([sys.executable, "-I", os.path.join(HERE, "olwin.py"), "wake", str(pid)], capture_output=True)
            for _ in range(40):
                if n_tap_clients() > before:
                    break
                wait_firewall(what="game client")
                time.sleep(1)
            else:
                continue
            break
        else:
            sys.exit(f"client {i} never reached the proxy (relay/tap running? OLMultiplayer.ini port 17778?)")
        # the proxy lists ports in connection order; take the newest one
        lines = [l for l in open(tap_log(), encoding="utf-8", errors="replace") if "new client" in l]
        port = int(lines[-1].split()[-1])
        hwnd, _ = window_rect(pid)
        u.MoveWindow(hwnd, 100 + 900 * i, 300, 816, 639, True)
        reg.append({"idx": i, "pid": pid, "hwnd": hwnd, "port": port, "log": os.path.join(LOGS, log)})
        print(f"  proxy port {port}, window moved", flush=True)
    save(reg)


def cp(idx, name, wait=True):
    c = clients()[idx]
    hwnd, rect = window_rect(c["pid"])
    x, y = rect[0], rect[1]
    olwin.focus(hwnd)
    time.sleep(0.4)
    log = c["log"]
    # precondition: the level is loaded and the hero streams (an F6 pressed while the level still loads is dropped and flips the overlay state)
    for _ in range(120):
        h = read_state()["heroes"].get(str(c["port"]))
        if h and time.time() - h["t"] < 3:
            break
        wait_firewall(what="game client")
        time.sleep(1)
    else:
        print(f"client {idx}: no hero state after 120 s, trying the overlay anyway")
    n0 = sum(1 for l in open(log, encoding="utf-8", errors="replace") if "Applying checkpoint" in l)
    olwin.tap(0x75)                    # F6: overlay on
    time.sleep(0.8)
    click(x + 558, y + 42)             # Checkpoints tab
    click(x + 250, y + 75)             # search box (its text survives between calls: clear it first)
    u.keybd_event(0x11, 0x1D, 0, 0)
    olwin.tap(0x41)                    # Ctrl+A
    u.keybd_event(0x11, 0x1D, 2, 0)
    olwin.tap(0x2E)                    # Delete
    type_text(name)
    time.sleep(0.6)
    click(x + 250, y + 166)            # first (only) result under its group header
    olwin.tap(0x75)                    # F6: overlay off
    if not wait:
        return True
    for _ in range(90):
        wait_firewall(what="game client")
        n = sum(1 for l in open(log, encoding="utf-8", errors="replace") if "Applying checkpoint" in l)
        if n > n0:
            time.sleep(4)
            return True
        time.sleep(1)
    print(f"client {idx}: checkpoint {name} not applied within 90 s (search matched nothing?)")
    return False


def _overlay_open(idx):
    c = clients()[idx]
    hwnd, rect = window_rect(c["pid"])
    olwin.focus(hwnd)
    time.sleep(0.4)
    olwin.tap(0x75)  # F6
    time.sleep(0.8)
    return rect[0], rect[1]


def maxhp(idx, value):
    """Set Max Health through the overlay slider (Player tab); the hero is healed to the new maximum."""
    x, y = _overlay_open(idx)
    click(x + 232, y + 42)
    u.SetCursorPos(x + 451, y + 519)
    time.sleep(0.2)
    u.keybd_event(0x11, 0x1D, 0, 0)
    time.sleep(0.05)
    u.mouse_event(2, 0, 0, 0, 0)
    time.sleep(0.08)
    u.mouse_event(4, 0, 0, 0, 0)
    u.keybd_event(0x11, 0x1D, 2, 0)
    time.sleep(0.3)
    olwin.tap(0x2E)
    type_text(str(value))
    olwin.tap(0x0D)
    time.sleep(0.5)
    olwin.tap(0x75)


def level_view(idx, tries=8):
    """Bring the camera pitch back to level, closed loop on the pitch the proxy decodes (pitch is a u16 angle, 65536 = 360 deg)."""
    c = clients()[idx]
    for _ in range(tries):
        h = read_state()["heroes"].get(str(c["port"]))
        if not h or "pitch" not in h:
            return
        p = h["pitch"] - 65536 if h["pitch"] > 32768 else h["pitch"]
        if abs(p) < 700:
            return
        counts = max(-200, min(200, -p / 45.0))     # positive mouse y = look down = negative pitch
        for _ in range(max(1, int(abs(counts) // 8))):
            u.mouse_event(1, 0, int(8 if counts > 0 else -8), 0, 0)
            time.sleep(0.02)
        time.sleep(0.6)


def nudge(idx, seconds=0.35, forward=True):
    """A short step forward. Spawned enemies that stand idle next to a motionless player notice the player once it moves."""
    c = clients()[idx]
    hwnd, _ = window_rect(c["pid"])
    olwin.focus(hwnd)
    time.sleep(0.3)
    vk, sc = (0x57, 0x11) if forward else (0x53, 0x1F)   # W or S
    u.keybd_event(vk, sc, 0, 0)
    time.sleep(seconds)
    u.keybd_event(vk, sc, 2, 0)


def spawn(idx, attack=True):
    """Spawn a Soldier in front of the hero (overlay: Spawns > Enemies > + > Spawn, then confirm placement with a click)."""
    x, y = _overlay_open(idx)
    click(x + 362, y + 42)    # Spawns tab
    click(x + 200, y + 170)   # Enemies
    click(x + 406, y + 578)   # +
    if not attack:
        click(x + 396, y + 210)   # 'Should Attack' checkbox off (it stays off for the rest of the session)
    click(x + 406, y + 538)   # Spawn -> placement mode
    olwin.tap(0x75)           # overlay off (placement ghost follows the crosshair)
    time.sleep(0.8)
    for _ in range(28):       # look down to the limit: the ghost lands on the floor at the hero's feet (enemies only attack within ~100-190 units)
        u.mouse_event(1, 0, 8, 0, 0)
        time.sleep(0.02)
    time.sleep(0.4)
    u.mouse_event(2, 0, 0, 0, 0)  # confirm
    time.sleep(0.15)
    u.mouse_event(4, 0, 0, 0, 0)
    time.sleep(0.6)
    u.mouse_event(8, 0, 0, 0, 0)  # right click: leave placement mode
    time.sleep(0.15)
    u.mouse_event(16, 0, 0, 0, 0)
    time.sleep(0.3)
    level_view(idx)


def embedded_relay(idx, port):
    """Start the relay built into OLGame.exe from the F6 overlay (Relay tab: port field, Start Relay). It only has room DEFAULT."""
    x, y = _overlay_open(idx)
    click(x + 483, y + 42)            # Relay tab
    click(x + 138, y + 99)            # port field
    u.keybd_event(0x11, 0x1D, 0, 0)
    olwin.tap(0x41)
    u.keybd_event(0x11, 0x1D, 2, 0)
    olwin.tap(0x2E)
    type_text(str(port))
    time.sleep(0.4)
    click(x + 143, y + 198)           # Start Relay
    time.sleep(2)
    wait_firewall(what="relay inside the game")
    olwin.tap(0x75)                   # overlay off


def enemies_of(state, port, since):
    out = {}
    for name, e in state["enemies"].items():
        key = f"C>R {port}"
        if key in e and e.get(key + " t", 0) >= since:
            out[name] = (e[key], e.get(key + " mode"))
    return out


def survey(idx, names):
    c = clients()[idx]
    for name in names:
        t0 = time.time()
        ok = cp(idx, name)
        time.sleep(6)
        s = read_state()
        h = s["heroes"].get(str(c["port"]))
        en = enemies_of(s, c["port"], t0)
        print(f"{name}: applied={ok} hero=" + (f"({h['x']:.0f},{h['y']:.0f},{h['z']:.0f})" if h else "?"), flush=True)
        for n, (p, mode) in sorted(en.items()):
            d = math.dist(p, (h["x"], h["y"], h["z"])) if h else -1
            print(f"    {n} at ({p[0]},{p[1]},{p[2]}) mode {mode} dist {d:.0f}", flush=True)
        if not en:
            print("    no enemies reported", flush=True)


def status():
    s = read_state()
    now = time.time()
    for c in clients():
        h = s["heroes"].get(str(c["port"]))
        alive = any(w["pid"] == c["pid"] for w in olwin.windows(c["pid"]))
        print(f"client {c['idx']} pid {c['pid']} port {c['port']} window={'yes' if alive else 'NO'} "
              + (f"hero ({h['x']:.0f},{h['y']:.0f},{h['z']:.0f}) hp {h['hp']} age {now - h['t']:.1f}s" if h else "no hero"))
    for name, e in s["enemies"].items():
        for k, p in e.items():
            if k.startswith("C>R") and not k.endswith((" mode", " t", " look")):
                print(f"  {name} owner {k.split()[1]} at {p} mode {e.get(k + ' mode')} age {now - e.get(k + ' t', 0):.1f}s")


def down(stack_only=False):
    # Only processes that belong to this test setup are stopped, found by the folder of their executable: the owner may be playing their
    # own Outlast (also named OLGame.exe) or running another relay, and a kill by name would end that too.
    game_root = GAME.replace("'", "''")
    work_root = os.path.dirname(HERE).replace("'", "''")
    own = ("Get-CimInstance Win32_Process -Filter \"Name='{name}'\" | Where-Object "
           "{{ $_.ExecutablePath -and $_.ExecutablePath.StartsWith('{root}', [StringComparison]::OrdinalIgnoreCase) }} | "
           "ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}")
    if not stack_only:
        subprocess.run(["powershell", "-NoProfile", "-Command", own.format(name="OLGame.exe", root=game_root)])
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    own.format(name="OpenOL_Relay.exe", root=work_root) + "; "
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object "
                    "{ $_.CommandLine -like '*udp_tap.py*' -or $_.CommandLine -like '*chaos.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"])
    save([])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "up":
        up()
    elif cmd == "launch":
        launch(int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "prison_persistent")
    elif cmd == "cp":
        sys.exit(0 if cp(int(sys.argv[2]), sys.argv[3]) else 1)
    elif cmd == "cpall":
        for i in range(len(clients())):
            cp(i, sys.argv[2])
    elif cmd == "embedded":
        embedded_relay(int(sys.argv[2]), int(sys.argv[3]))
    elif cmd == "maxhp":
        maxhp(int(sys.argv[2]), int(sys.argv[3]))
    elif cmd == "spawn":
        spawn(int(sys.argv[2]))
    elif cmd == "nudge":
        nudge(int(sys.argv[2]))
    elif cmd == "level":
        level_view(int(sys.argv[2]))
    elif cmd == "survey":
        survey(int(sys.argv[2]), sys.argv[3:])
    elif cmd == "status":
        status()
    elif cmd == "down":
        down()
    else:
        sys.exit(__doc__)
