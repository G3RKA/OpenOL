"""python -I click.py X Y  — real left click at screen coords (full resolution)."""
import ctypes, sys, time
u = ctypes.windll.user32
x, y = int(sys.argv[1]), int(sys.argv[2])
u.SetCursorPos(x, y); time.sleep(0.2)
u.mouse_event(2, 0, 0, 0, 0); time.sleep(0.08); u.mouse_event(4, 0, 0, 0, 0)
