"""A checkpoint load that arrives at a client which is still starting (exe patch: the shared checkpoint follow waits for a ticking world and a hero).

  python -I follow_race.py [<checkpoint>]      default Prison_IsolationCells02_Soldier (a checkpoint whose actor is not in the streamed world at start)

Two clients are launched; the load is sent to client 0 at once, while client 1 is still starting up. Without the wait the engine of client 1 asserted
("Sequence != RootSequence", UnWorld.cpp 1693) in the cross-map travel. Hands-free: mailbox only.

  R1  client 1 is still alive 60 s after the load
  R2  client 1 applied the checkpoint (the follow ran after the wait)
  R3  client 0 is alive and its hero stream is fresh
  (info) cnt_follow_deferred: how many frames client 1 kept the request waiting; 0 means the race did not happen in this run
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol, olmail
from sweep import load

results = []


def check(name, ok, why=""):
    results.append(ok)
    print(f"RESULT {'PASS' if ok else 'FAIL'} {name} {why}".rstrip(), flush=True)


def has(c, text):
    try:
        return text in open(c["log"], encoding="utf-8", errors="replace").read()
    except OSError:
        return False


def main():
    cp = sys.argv[1] if len(sys.argv) > 1 else "Prison_IsolationCells02_Soldier"
    ol.up()
    ol.launch(2, "prison_persistent")
    cs = ol.clients()
    load(cs[0], cp)
    time.sleep(60)
    m1 = olmail.read(cs[1]["pid"])
    alive1 = bool(m1) and bool(m1.get("hooks_ran")) and not has(cs[1], "Critical: appError")
    check("R1.client-1-alive-after-the-early-load", alive1, f"hooks_ran {m1.get('hooks_ran') if m1 else None}")
    check("R2.client-1-applied-the-checkpoint", has(cs[1], f"GS - Applying checkpoint {cp}"), "follow ran after the wait")
    st = ol.read_state()
    h = st["heroes"].get(str(cs[0]["port"]))
    check("R3.client-0-alive-and-streaming", bool(h) and time.time() - h["t"] < 5, "hero stream fresh")
    print(f"INFO cnt_follow_deferred on client 1: {m1.get('cnt_follow_deferred') if m1 else None}, executed {m1.get('cnt_follow_exec') if m1 else None}", flush=True)
    ol.down()
    print(f"SUMMARY {sum(results)}/{len(results)}", flush=True)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
