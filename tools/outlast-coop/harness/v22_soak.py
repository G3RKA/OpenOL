"""Soak of the OpenOL 2.2.0 test copy: relay plus two clients on a map; every 30 s both clients and the relay alive, no new Critical / Assertion / fatal
lines, no disconnect, memory; the multiplayer lines that matter (AI owner changes, reconnects) are printed when they appear.

  python -I v22_soak.py <minutes> [<map>]
"""
import os, re, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v22

BAD = re.compile(r"Critical|Assertion failed|Fatal error|Unhandled Exception|Access violation", re.I)
NOTE = re.compile(r"Enemy AI owner|Disconnected|Connection lost|reconnect|Kicked|SESS_|Session", re.I)


def mem_mb(pid):
    out = subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).WorkingSet64"], capture_output=True, text=True).stdout.strip()
    return int(out) // 2**20 if out.isdigit() else None


def main():
    minutes = float(sys.argv[1])
    mapname = sys.argv[2] if len(sys.argv) > 2 else "prison_persistent"
    reg = v22.up(2, mapname)
    cs = reg["clients"]
    time.sleep(20)
    seen = [len(v22.read_log(c["log"])) for c in cs]
    mem0 = [mem_mb(c["pid"]) for c in cs]
    anomalies, n = [], 0
    t0 = time.time()
    while time.time() - t0 < minutes * 60:
        time.sleep(30)
        n += 1
        row = []
        for i, c in enumerate(cs):
            data = v22.read_log(c["log"])
            new = data[seen[i]:]
            seen[i] = len(data)
            for l in new.splitlines():
                if BAD.search(l):
                    anomalies.append((n, i, l[:160]))
                if NOTE.search(l):
                    print(f"    c{i}: {l[:170]}", flush=True)
            if not v22.alive(c["pid"]):
                anomalies.append((n, i, "process gone"))
            row.append(f"c{i} mem {mem_mb(c['pid'])}")
        if not v22.alive(reg["relay"]):
            anomalies.append((n, -1, "relay gone"))
        print(f"[{n * 30:4d}s] " + " | ".join(row), flush=True)
    print(f"SUMMARY samples {n}, anomalies {len(anomalies)}, memory MB {mem0} -> {[mem_mb(c['pid']) for c in cs]}", flush=True)
    for a in anomalies[:20]:
        print("ANOMALY", a, flush=True)
    v22.down()
    sys.exit(1 if anomalies else 0)


if __name__ == "__main__":
    main()
