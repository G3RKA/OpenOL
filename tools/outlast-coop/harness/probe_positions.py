"""Where are the enemies and the puppets, second by second, after a checkpoint is loaded on both clients (one after the other, as the sweep does).

  python -I probe_positions.py <checkpoint> [<checkpoint before it> | -] [<seconds between the two loads>]      no mouse, no keyboard

Prints for each second: per client its own enemies (class tail, x, y) and its puppets (owner id, x, y), the closest own-to-puppet distance
between the clients, and the patch counters (merges, re-announcements).
"""
import math, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol, census, olmail
from sweep import load, PERSIST


def snap(cs):
    out = []
    for c in cs:
        r = census.census(c["pid"])
        own = [(e["class"][-4:], e["x"], e["y"]) for e in census.alive_own(r)]
        pup = [(p["owner"], p["actor"]["x"], p["actor"]["y"]) for p in census.alive_puppets(r)]
        out.append((own, pup))
    return out


def main():
    target = sys.argv[1]
    before = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    delay = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0     # seconds between the two clients' loads: lets the first client's enemy walk away
    ol.up()
    ol.launch(2, "prison_persistent")
    cs = ol.clients()
    for c in cs:
        olmail.set_disable(c["pid"], 4)          # no shared checkpoint: load both ourselves, in sequence, like the sweep
    if before:
        for c in cs:
            load(c, before)
        time.sleep(8)
    for c in cs:
        print(f"load {target} on client {c['idx']}: {load(c, target)}", flush=True)
        if c["idx"] == 0 and delay:
            time.sleep(delay)
    for sec in range(25):
        s = snap(cs)
        (a_own, a_pup), (b_own, b_pup) = s
        d = [round(math.dist(o[1:], q[1:])) for o in a_own for q in b_own]
        print(f"t+{sec:2d}s  A own {a_own} pup {a_pup} | B own {b_own} pup {b_pup} | A-own to B-own distances {sorted(d)}", flush=True)
        time.sleep(1)
    for c in cs:
        m = olmail.read(c["pid"])
        print("client", c["idx"], {k: m.get(k) for k in ("cnt_own_destroyed", "cnt_puppet_destroyed", "cnt_rebroadcast")}, flush=True)
    ol.down()


if __name__ == "__main__":
    main()
