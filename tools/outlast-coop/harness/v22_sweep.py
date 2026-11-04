"""Sweep of checkpoints with enemies on the OpenOL 2.2.0 test copy, judged from the game logs (the 2.2.0 traffic is encrypted and the exe has no data area).

  python -I v22_sweep.py <checkpoint>...        needs `v22.py up 2` first (clients registered in v22_reg.json); loads alternate between the two clients (overlay, mouse)

Per checkpoint, after the load on one client and the follow on the other (the 2.2.0 session travel):
  followed   the other client applied the same checkpoint
  factory    "[MP] Enemy factory X: spawn" / "not the owner" lines per client since the load: with one AI owner only ONE client may spawn enemies
  dup        both clients spawned enemies of their own: a duplicated enemy
  anim       "Dummy ... plays" lines (a puppet plays the owner's animation) and "Enemy anim not found" lines (failures)
  bad        Critical / Assertion lines, and whether both processes are alive
"""
import os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v22, v22_cp

BAD = re.compile(r"Critical|Assertion failed|Fatal error|Unhandled Exception|Access violation", re.I)


def count(text, pat):
    return len(re.findall(pat, text))


def main():
    reg = v22.load()
    cs = reg["clients"]
    for i, c in enumerate(cs):
        v22_cp.place(c, i)
    rows = []
    for k, name in enumerate(sys.argv[1:]):
        loader, other = k % 2, 1 - k % 2
        marks = [len(v22.read_log(c["log"])) for c in cs]
        ok = v22_cp.cp(cs[loader], name)
        followed = False
        for _ in range(90):
            if f"Applying checkpoint {name}" in v22.read_log(cs[other]["log"])[marks[other]:]:
                followed = True
                break
            time.sleep(1)
        time.sleep(12)
        txt = [v22.read_log(c["log"])[marks[i]:] for i, c in enumerate(cs)]
        spawn = [count(t, r"Enemy factory \S+: spawn") for t in txt]
        notown = [count(t, r"Enemy factory \S+: not the owner") for t in txt]
        plays = [count(t, r"Dummy \S+ plays") for t in txt]
        nf = [count(t, r"Enemy anim not found") for t in txt]
        bad = [count(t, BAD.pattern) for t in txt]
        alive = [v22.alive(c["pid"]) for c in cs]
        dup = all(s > 0 for s in spawn)
        print(f"{name:40s} loader c{loader} applied={ok} followed={followed} spawn={spawn} not_owner={notown} dummy_plays={plays} anim_not_found={nf} bad={bad} alive={alive}{' DUP' if dup else ''}", flush=True)
        rows.append((name, ok, followed, dup, sum(nf), sum(bad), all(alive)))
        if not all(alive):
            print("a client died; stopping", flush=True)
            break
    print(f"SUMMARY {len(rows)} checkpoints, not applied {sum(1 for r in rows if not r[1])}, not followed {sum(1 for r in rows if not r[2])}, "
          f"duplicates {sum(1 for r in rows if r[3])}, anim-not-found {sum(r[4] for r in rows)}, bad lines {sum(r[5] for r in rows)}", flush=True)


if __name__ == "__main__":
    main()
