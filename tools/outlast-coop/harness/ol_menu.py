"""The real player path through the main menu, for the natural-progress tests (no F6 overlay, no map URL):
Multiplayer -> Connect, then New Game (Main, Normal). Keyboard for the lists, relative mouse moves for the buttons (the menu cursor is virtual).

  python -I ol_menu.py <n_clients>      # needs ol.up() first; leaves the clients at the start of the game (the car)
"""
import os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol

u = ol.u
VK_DOWN, VK_LEFT, VK_ENTER, VK_ESC = 0x28, 0x25, 0x0D, 0x1B


def _log_has(path, text):
    try:
        return text in open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return False


def launch_menu(i):
    """Start client i at the main menu (no map URL). Returns the registry entry (port is known after connect)."""
    log = f"mp_{chr(97 + i)}.log"
    pid = int(subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Start-Process -FilePath '{ol.GAME}\\OLGame.exe' -WorkingDirectory '{ol.GAME}' -PassThru "
         f"-ArgumentList '-nostartupmovies','-nosteam','-FORCELOGFLUSH','-log={log}').Id"],
        capture_output=True, text=True).stdout.strip())
    logp = os.path.join(ol.LOGS, log)
    for _ in range(90):
        if _log_has(logp, "Wwise(R) SDK Version"):
            break
        time.sleep(1)
    for _ in range(8):
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "olwin.py"), "wake", str(pid)], capture_output=True)
        time.sleep(3)
        if _log_has(logp, "Menu") or _log_has(logp, "MainMenu"):
            break
    hwnd, _r = ol.window_rect(pid)
    u.MoveWindow(hwnd, 100 + 900 * i, 300, 816, 639, True)
    time.sleep(8)       # let the menu finish loading
    return {"idx": i, "pid": pid, "hwnd": hwnd, "port": None, "log": logp}


def _focus(c):
    for _ in range(8):
        if ol.olwin.focus(c["hwnd"]):
            break
        time.sleep(0.7)
    else:
        print(f"warning: could not take the foreground for client {c['idx']}", flush=True)
    time.sleep(0.5)


def _keys(*vks):
    for vk in vks:
        ol.olwin.tap(vk)
        time.sleep(0.8)


def _move(dx, dy):
    n = max(abs(dx), abs(dy)) // 10 + 1
    for _ in range(n):
        u.mouse_event(1, dx // n, dy // n, 0, 0)
        time.sleep(0.02)


def _click_at(x, y):
    """Click the menu item at window pixel (x, y) of an 816x639 window; the virtual cursor is first parked in the top-left corner."""
    _move(-1500, -1500)
    _move(x - 12, y - 43)
    time.sleep(0.4)
    _move(3, 2)
    time.sleep(0.3)
    _move(-3, -2)
    time.sleep(0.5)
    u.mouse_event(2, 0, 0, 0, 0)
    time.sleep(0.1)
    u.mouse_event(4, 0, 0, 0, 0)
    time.sleep(1.2)


def connect(c):
    """Multiplayer -> Connect with whatever is in OLMultiplayer.ini; returns when the client is registered by the proxy."""
    before = ol.n_tap_clients()
    _focus(c)
    _click_at(408, 417)             # Multiplayer
    time.sleep(2)
    _click_at(506, 476)             # Connect
    for _ in range(40):
        ol.wait_firewall(what="game client")
        if _log_has(c["log"], "MpConn: Connected!") and ol.n_tap_clients() > before:
            break
        time.sleep(1)
    else:
        sys.exit("client never connected (relay up? ini port?)")
    lines = [l for l in open(ol.tap_log(), encoding="utf-8", errors="replace") if "new client" in l]
    c["port"] = int(lines[-1].split()[-1])
    time.sleep(2)


def new_game(c):
    """Main menu -> New Game -> Main -> Normal -> Continue (intro text); the story starts at checkpoint StartGame."""
    _focus(c)
    _click_at(408, 335)             # New Game
    time.sleep(2)
    _click_at(336, 376)             # Main (not the DLC)
    time.sleep(2)
    _keys(VK_ENTER)                 # Normal (already highlighted)
    time.sleep(3)
    _keys(VK_ENTER)                 # Continue after the intro text


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    reg = []
    for i in range(n):
        c = launch_menu(i)
        reg.append(c)
        connect(c)
        print(f"client {i}: pid {c['pid']} connected, proxy port {c['port']}", flush=True)
    ol.save(reg)
    for c in reg:
        new_game(c)
    print("new game started on", n, "client(s)")


if __name__ == "__main__":
    main()
