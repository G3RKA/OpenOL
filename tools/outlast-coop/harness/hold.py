"""python -I hold.py KEY SECONDS — hold a key (w/a/s/d/e/shift/ctrl) as real input."""
import ctypes, sys, time
u = ctypes.windll.user32
VK = {"w": (0x57, 0x11), "a": (0x41, 0x1E), "s": (0x53, 0x1F), "d": (0x44, 0x20),
      "e": (0x45, 0x12), "shift": (0x10, 0x2A), "ctrl": (0x11, 0x1D), "space": (0x20, 0x39)}
vk, sc = VK[sys.argv[1]]
u.keybd_event(vk, sc, 0, 0); time.sleep(float(sys.argv[2])); u.keybd_event(vk, sc, 2, 0)
