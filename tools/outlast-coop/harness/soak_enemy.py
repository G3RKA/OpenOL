"""Soak with enemies on the patched exe, hands-free: two clients, one checkpoint with enemies loaded through the mailbox, then every 30 s
both processes alive, hero streams fresh, patch counters, memory, new error lines in the game logs. Prints a line per sample and a summary.

  python -I soak_enemy.py <checkpoint> <minutes>
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol, olmail
from sweep import load
from soak import mem_mb

BAD = ("Animation Not Found", "Fatal error", "Assertion failed", "Access violation", "Unhandled Exception")
KEYS = ("hooks_ran", "cnt_own_destroyed", "cnt_puppet_destroyed", "cnt_anim_sent", "cnt_anim_recv", "cnt_anim_played", "cnt_anim_dropped",
        "cnt_trig_seen", "cnt_trig_dropped")


def bad_lines(c, start):
    try:
        text = open(c["log"], encoding="utf-8", errors="replace").read()[start:]
    except OSError:
        return 0
    return sum(text.count(b) for b in BAD)


def main():
    cp, minutes = sys.argv[1], float(sys.argv[2])
    ol.up()
    ol.launch(2, "prison_persistent")
    cs = ol.clients()
    for c in cs:
        if not load(c, cp):
            print("FAIL load", c["idx"], flush=True)
    time.sleep(10)
    starts = [os.path.getsize(c["log"]) for c in cs]
    mem0 = [mem_mb(c["pid"]) for c in cs]
    anomalies, n = [], 0
    t0 = time.time()
    while time.time() - t0 < minutes * 60:
        time.sleep(30)
        n += 1
        st = ol.read_state()
        row = []
        for i, c in enumerate(cs):
            alive = olmail.read(c["pid"])
            hero = st["heroes"].get(str(c["port"]))
            fresh = bool(hero) and time.time() - hero["t"] <= 5
            bad = bad_lines(c, starts[i])
            m = mem_mb(c["pid"])
            if not alive or not alive.get("hooks_ran"):
                anomalies.append((n, i, "no data area"))
            if not fresh:
                anomalies.append((n, i, "hero stream stale"))
            if bad:
                anomalies.append((n, i, f"bad log lines {bad}"))
            row.append(f"c{i} mem {m} hp {hero.get('hp') if hero else None} " + " ".join(f"{k[4:] if k.startswith('cnt_') else k}={alive.get(k)}" for k in KEYS[1:] if alive and alive.get(k)))
        print(f"[{n * 30:4d}s] " + " | ".join(row), flush=True)
    mem1 = [mem_mb(c["pid"]) for c in cs]
    print(f"SUMMARY samples {n}, anomalies {len(anomalies)}, memory MB {mem0} -> {mem1}", flush=True)
    for a in anomalies[:20]:
        print("ANOMALY", a, flush=True)
    ol.down()
    sys.exit(1 if anomalies else 0)


if __name__ == "__main__":
    main()
