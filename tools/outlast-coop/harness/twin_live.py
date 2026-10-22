"""Live runtime twin: ONE launch of two clients, the one-owner rule switched on and off in memory (olmail.py), counted with the memory census.

  python -I twin_live.py        needs the patched exe with a data area; uses the F6 overlay (real mouse and keyboard)

Round 1 (rule on): both load a checkpoint with a map patient -> exactly one enemy in total, the merge counters moved.
Round 2 (rule off, set from outside): both load another checkpoint with a patient -> every client keeps its own copy and a puppet (the original bug).
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol, census, olmail


def snapshot(label):
    cs = ol.clients()
    out = []
    for c in cs:
        r = census.census(c["pid"])
        d = olmail.read(c["pid"])
        out.append((len(census.alive_own(r)), len(census.alive_puppets(r)), d))
    own, pup = [x[0] for x in out], [x[1] for x in out]
    print(f"{label}: own {own}, puppets {pup}, total enemies seen {[o + p for o, p in zip(own, pup)]}; counters "
          + str([{k: x[2].get(k) for k in ('cnt_apply_calls', 'cnt_send_calls', 'cnt_own_destroyed', 'cnt_puppet_destroyed')} for x in out]), flush=True)
    return out


def main():
    ol.up()
    ol.launch(2, "prison_persistent")
    cs = ol.clients()
    for c in cs:
        d = olmail.read(c["pid"])
        print("client", c["idx"], "data area:", {k: d.get(k) for k in ("hooks_ran", "disable", "magic")}, flush=True)
    for i in range(2):
        olmail.set_disable(cs[i]["pid"], 0)
    for i in range(2):
        ol.cp(i, "Prison_OldCells_PreStruggle2")
    time.sleep(12)
    r1 = snapshot("rule ON ")
    for i in range(2):
        olmail.set_disable(cs[i]["pid"], 1)
    for i in range(2):
        ol.cp(i, "Prison_OldCells_PreStruggle")
    time.sleep(12)
    r2 = snapshot("rule OFF")
    for i in range(2):
        olmail.set_disable(cs[i]["pid"], 0)
    ok1 = sum(x[0] + x[1] for x in r1) == 2 and r1[0][0] + r1[1][0] == 1                       # one real enemy, seen as real on one client and as a puppet on the other
    ok2 = all(x[0] >= 1 and x[1] >= 1 for x in r2)                                              # the original behaviour: every client has its own copy and a puppet
    print("RESULT twin-rule-on-gives-one-owner", "PASS" if ok1 else "FAIL")
    print("RESULT twin-rule-off-brings-the-bug-back", "PASS" if ok2 else "FAIL")
    ol.down()


if __name__ == "__main__":
    main()
