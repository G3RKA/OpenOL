"""Turn a client's hero to an absolute yaw (or by a delta with +/-), closed loop on tap state.

  python -I turn.py <window_pid> <client_port> <yaw | +delta | -delta> [state=state.json]
"""
import subprocess
import sys
import time

from_here = __file__.rsplit("\\", 1)[0] if "\\" in __file__ else "."
sys.path.insert(0, from_here)
import goto  # noqa: E402  (same folder; -I drops cwd, so the path is added explicitly)


def main():
    wpid, port, arg = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    statef = sys.argv[4] if len(sys.argv) > 4 else "state.json"
    subprocess.run([sys.executable, "-I", f"{from_here}\\olwin.py", "focus", str(wpid)], capture_output=True)
    time.sleep(0.3)
    h = goto.fresh(port, statef, time.time())
    target = (h["yaw"] + int(arg)) % 65536 if arg[0] in "+-" else int(arg) % 65536
    k = 45.0  # yaw units per mouse count, from goto calibration; loop corrects the rest
    for i in range(12):
        err = goto.yaw_err(target, h["yaw"])
        print(f"turn {i}: yaw={h['yaw']} target={target} err={err}")
        if abs(err) < 400:
            return 0
        goto.mouse_dx(max(-400, min(400, err / k)))
        t = time.time()
        time.sleep(0.2)
        h = goto.fresh(port, statef, t)
    return 1


if __name__ == "__main__":
    sys.exit(main())
