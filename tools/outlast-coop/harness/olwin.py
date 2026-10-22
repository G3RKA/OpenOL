"""Drive OLGame.exe windows for local two-instance tests (Windows only, ctypes, no deps).

  python -I olwin.py list
  python -I olwin.py focus <pid>
  python -I olwin.py wake <pid>                  # right after launch: unblocks engine init
  python -I olwin.py key <pid> enter|tilde|esc
  python -I olwin.py console <pid> "<command>"   # focus, then Tilde, chars, Enter

UE3 defers window messages and handles them on its tick, so the target must not be stalled:
`console` brings the window to the foreground first.
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x0100, 0x0101, 0x0102
VK_MENU, VK_RETURN, VK_OEM_3 = 0x12, 0x0D, 0xC0
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x2, 0x4
SW_RESTORE = 9


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]



user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.MapVirtualKeyW.restype = wt.UINT
EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def ol_pids():
    import subprocess
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq OLGame.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return [int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"OLGame')]


def windows(pid=None):
    found = []

    def cb(hwnd, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if user32.IsWindowVisible(hwnd) and (pid is None or p.value == pid):
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, 256)
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            found.append(dict(hwnd=hwnd, pid=p.value, cls=cls.value, title=title.value,
                              rect=(r.left, r.top, r.right - r.left, r.bottom - r.top),
                              iconic=bool(user32.IsIconic(hwnd))))
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return found


def main_window(pid):
    ws = windows(pid)
    if not ws:
        sys.exit(f"no visible window for pid {pid}")
    return max(ws, key=lambda w: w["rect"][2] * w["rect"][3])["hwnd"]


def focus(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    # Tapping Alt lifts the foreground lock for a background process.
    user32.keybd_event(VK_MENU, 0, 0, 0)
    ok = user32.SetForegroundWindow(hwnd)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    return bool(ok) and user32.GetForegroundWindow() == hwnd


def key(hwnd, vk):
    scan = user32.MapVirtualKeyW(vk, 0)
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 1 | (scan << 16))
    user32.PostMessageW(hwnd, WM_KEYUP, vk, 1 | (scan << 16) | (0xC0 << 24))


def tap(vk):
    """Real keypress via keybd_event; goes to the foreground window."""
    scan = user32.MapVirtualKeyW(vk, 0)
    user32.keybd_event(vk, scan, 0, 0)
    time.sleep(0.08)
    user32.keybd_event(vk, scan, KEYEVENTF_KEYUP, 0)
    time.sleep(0.25)


def real_console(text):
    """Tilde, text, Enter as real input (the game ignores posted key messages)."""
    tap(VK_OEM_3)
    for ch in text:
        # KEYEVENTF_UNICODE: independent of the active keyboard layout (owner may be on RU).
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            inp = INPUT(type=1, ki=KEYBDINPUT(0, ord(ch), flags, 0, None))
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        time.sleep(0.03)
    tap(VK_RETURN)


def console(hwnd, text):
    key(hwnd, VK_OEM_3)
    time.sleep(0.3)
    for ch in text:
        user32.PostMessageW(hwnd, WM_CHAR, ord(ch), 1)
    time.sleep(0.1)
    key(hwnd, VK_RETURN)
    user32.PostMessageW(hwnd, WM_CHAR, 13, 1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        fg = user32.GetForegroundWindow()
        for pid in ol_pids():
            for w in windows(pid):
                print(pid, hex(w["hwnd"]), w["cls"], repr(w["title"]), w["rect"],
                      "iconic" if w["iconic"] else "", "FOREGROUND" if w["hwnd"] == fg else "")
    elif cmd == "focus":
        print("focused" if focus(main_window(int(sys.argv[2]))) else "focus FAILED")
    elif cmd == "wake":
        # Launched from a background shell the window starts minimized and engine init
        # blocks (after Wwise, before D3D) until it is restored. Minimize+restore unblocks it.
        pid = int(sys.argv[2])
        for _ in range(60):
            if windows(pid):
                break
            time.sleep(1)
        h = main_window(pid)
        user32.ShowWindow(h, 6)  # SW_MINIMIZE
        time.sleep(1)
        user32.ShowWindow(h, SW_RESTORE)
        print("woken", hex(h), "focused" if focus(h) else "focus FAILED")
    elif cmd == "key":
        h = main_window(int(sys.argv[2]))
        print("focused" if focus(h) else "focus FAILED")
        time.sleep(0.5)
        tap({"enter": VK_RETURN, "tilde": VK_OEM_3, "esc": 0x1B, "down": 0x28, "up": 0x26, "left": 0x25, "right": 0x27, "space": 0x20, "tab": 0x09, "f6": 0x75, "slash": 0xBF}[sys.argv[3]])
        print("sent")
    elif cmd == "console":
        h = main_window(int(sys.argv[2]))
        print("focused" if focus(h) else "focus FAILED")
        time.sleep(1.0)
        real_console(sys.argv[3])
        print("sent")
    else:
        sys.exit(__doc__)
