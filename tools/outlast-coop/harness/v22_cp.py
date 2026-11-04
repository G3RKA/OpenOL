"""Load a checkpoint through the F6 overlay on a 2.2.0 client (the 2.1.0 click sequence of ol.cp, but without the proxy state: the registry is v22_reg.json).

  python -I v22_cp.py <client idx> <checkpoint>        (the window must be 816x639; v22.py up places nothing, so this moves the window first)
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol, olwin, v22


def place(c, i):
    hwnd, _ = ol.window_rect(c["pid"])
    ol.u.MoveWindow(hwnd, 100 + 900 * i, 300, 816, 639, True)
    time.sleep(1)
    return hwnd


def cp(c, name, i=None):
    hwnd, rect = ol.window_rect(c["pid"])
    x, y = rect[0], rect[1]
    olwin.focus(hwnd)
    time.sleep(0.4)
    n0 = v22.read_log(c["log"]).count("Applying checkpoint")
    olwin.tap(0xC0)                    # ~ (VK_OEM_3): overlay on (2.2.0; F6 opens the engine console)
    time.sleep(0.8)
    ol.click(x + 558, y + 42)          # Checkpoints tab
    ol.click(x + 250, y + 75)          # search box
    ol.u.keybd_event(0x11, 0x1D, 0, 0)
    olwin.tap(0x41)                    # Ctrl+A
    ol.u.keybd_event(0x11, 0x1D, 2, 0)
    olwin.tap(0x2E)                    # Delete
    ol.type_text(name)
    time.sleep(0.6)
    ol.click(x + 250, y + 166)         # first result
    olwin.tap(0xC0)                    # ~: overlay off
    for _ in range(90):
        if v22.read_log(c["log"]).count("Applying checkpoint") > n0:
            time.sleep(4)
            return True
        time.sleep(1)
    return False


if __name__ == "__main__":
    c = v22.load()["clients"][int(sys.argv[1])]
    place(c, int(sys.argv[1]))
    print("applied" if cp(c, sys.argv[2]) else "NOT applied", flush=True)
