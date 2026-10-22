"""python -I look.py DX DY [steps] — relative mouse move (game camera) in small steps."""
import ctypes, sys, time
u = ctypes.windll.user32
dx, dy = int(sys.argv[1]), int(sys.argv[2])
n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
for _ in range(n):
    u.mouse_event(1, dx // n, dy // n, 0, 0)
    time.sleep(0.02)
