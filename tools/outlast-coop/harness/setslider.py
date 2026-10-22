"""python -I setslider.py X Y VALUE — ctrl+click an ImGui slider at screen X,Y and type a value."""
import ctypes, sys, time
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
import olwin
u = ctypes.windll.user32
x, y, val = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
u.SetCursorPos(x, y); time.sleep(0.2)
u.keybd_event(0x11, 0x1D, 0, 0); time.sleep(0.05)
u.mouse_event(2, 0, 0, 0, 0); time.sleep(0.08); u.mouse_event(4, 0, 0, 0, 0); time.sleep(0.05)
u.keybd_event(0x11, 0x1D, 2, 0); time.sleep(0.3)
olwin.tap(0x2E)  # Delete: ctrl+click selects the current text
for ch in val:
    for fl in (4, 6):
        inp = olwin.INPUT(type=1, ki=olwin.KEYBDINPUT(0, ord(ch), fl, 0, None))
        u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(olwin.INPUT))
    time.sleep(0.05)
olwin.tap(0x0D)
