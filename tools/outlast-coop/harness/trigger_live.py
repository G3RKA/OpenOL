"""Story triggers from a far-away player, hands-free (exe patch: trigger distance gate, kill switch bit 5 = 32).

  python -I trigger_live.py          two clients and a scripted third peer, no mouse and no keyboard; the relay is the UPSTREAM one (no relay patch)

The scripted peer stands at a chosen position (a real hero packet of the proxy state, moved) and sends one WORLD_TRIGGER_ACT for a repeatable trigger
of the Admin_Explosion level. The clients load that checkpoint through the patch's mailbox (olmail.py), so the old overlay-driven group B is not needed.

  T1  a trigger from a peer that is unknown to the clients' position table (no hero packet yet) fires on both clients (the gate lets unknown positions through)
  T2  the same trigger from a peer standing 50000 units away is dropped by BOTH clients (the gate, counters cnt_trig_dropped)
  T3  control: from a peer standing at the players' position it fires on both clients
  T4  twin: with the gate switched off (disable bit 5) the far peer's trigger fires on both clients (the upstream behaviour)
  T5  both processes alive
"""
import os, re, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol, olmail
from sweep import load

DISABLE_TRIGGER = 32
PY = [sys.executable, "-I"]
PATH = "center_block_sript.TheWorld:PersistentLevel.Main_Sequence.SeqEvent_Touch_3"
MARKER = "ForceActivateTouchEvent: SeqEvent_Touch_3 "
results = []


def check(name, ok, why=""):
    results.append(ok)
    print(f"RESULT {'PASS' if ok else 'FAIL'} {name} {why}".rstrip(), flush=True)


def fired(c):
    return open(c["log"], encoding="utf-8", errors="replace").read().count(MARKER)


def send(extra):
    r = subprocess.run(PY + [os.path.join(HERE, "fake_peer.py"), "127.0.0.1", "17778", "PUBLIC", *extra], capture_output=True, text=True, timeout=60)
    return r.returncode == 0


def case(cs, label, extra):
    before = [fired(c) for c in cs]
    ok = send(extra)
    time.sleep(4)
    delta = [fired(c) - b for c, b in zip(cs, before)]
    return ok, delta


def main():
    ol.up()
    ol.launch(2, "prison_persistent")
    cs = ol.clients()
    for c in cs:
        olmail.set_disable(c["pid"], 4)                    # shared checkpoint off: both clients load the checkpoint themselves
    for c in cs:
        load(c, "Admin_Explosion")
    time.sleep(8)
    h = ol.read_state()["heroes"].get(str(cs[0]["port"]))
    st = os.path.join(HERE, "state.json")
    time.sleep(8)                                          # a repeatable trigger is dropped while its Kismet chain plays
    ok, d = case(cs, "T1", ["trigger", PATH])
    check("T1.unknown-position-peer-trigger-fires-on-both", ok and all(x >= 1 for x in d), f"fired {d}")
    time.sleep(8)
    ok, d = case(cs, "T2", ["trigger-at", PATH, str(h["x"] + 50000), str(h["y"]), str(h["z"]), st])
    m = [olmail.read(c["pid"]) for c in cs]
    check("T2.far-peer-trigger-is-dropped-by-both", ok and all(x == 0 for x in d) and all(x.get("cnt_trig_dropped", 0) >= 1 for x in m),
          f"fired {d}, dropped {[x.get('cnt_trig_dropped') for x in m]}, seen {[x.get('cnt_trig_seen') for x in m]}")
    ok, d = case(cs, "T3", ["trigger-at", PATH, str(h["x"]), str(h["y"]), str(h["z"]), st])
    check("T3.control-near-peer-trigger-fires-on-both", ok and all(x >= 1 for x in d), f"fired {d}")
    time.sleep(8)
    for c in cs:
        olmail.set_disable(c["pid"], 4 | DISABLE_TRIGGER)
    ok, d = case(cs, "T4", ["trigger-at", PATH, str(h["x"] + 50000), str(h["y"]), str(h["z"]), st])
    check("T4.twin-gate-off-the-far-trigger-fires", ok and all(x >= 1 for x in d), f"fired {d}")
    alive = [olmail.read(c["pid"]).get("hooks_ran") for c in cs]
    check("T5.both-clients-alive", all(alive), f"{alive}")
    ol.down()
    print(f"SUMMARY {sum(results)}/{len(results)}", flush=True)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
