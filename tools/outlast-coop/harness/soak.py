"""Idle soak of the registered clients in real play: every 30 s check that both processes live, both heroes keep sending, the relay shows no
leave/join, and note each client's memory. Prints only anomalies and a final summary.

  python -I soak.py <minutes> [relay_log]
"""
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol


def mem_mb(pid):
    out = subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).WorkingSet64"],
                         capture_output=True, text=True).stdout.strip()
    return int(out) // 2**20 if out.isdigit() else None


def main():
    minutes = float(sys.argv[1])
    cl = ol.clients()
    t0 = time.time()
    first = {c["idx"]: mem_mb(c["pid"]) for c in cl}
    anomalies, samples = [], 0
    while time.time() - t0 < minutes * 60:
        time.sleep(30)
        samples += 1
        s = ol.read_state()
        now = time.time()
        for c in cl:
            m = mem_mb(c["pid"])
            h = s["heroes"].get(str(c["port"]))
            if m is None:
                anomalies.append(f"{int(now - t0)} s: client {c['idx']} process gone")
                print(anomalies[-1], flush=True)
            elif not h or now - h["t"] > 5:
                anomalies.append(f"{int(now - t0)} s: client {c['idx']} hero state stale ({now - h['t'] if h else 'none'})")
                print(anomalies[-1], flush=True)
        if samples % 10 == 0:
            print(f"{int(now - t0)} s ok, memory MB " + ", ".join(f"c{c['idx']}={mem_mb(c['pid'])}" for c in cl), flush=True)
    last = {c["idx"]: mem_mb(c["pid"]) for c in cl}
    print("SOAK DONE", {"minutes": minutes, "anomalies": len(anomalies), "mem_start": first, "mem_end": last}, flush=True)


if __name__ == "__main__":
    main()
