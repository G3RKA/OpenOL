"""Shared checkpoint loads, hands-free: a checkpoint loaded on ONE client must be loaded by the partner too (patch v4, WORLD_CHECKPOINT_LOAD 0x11).

  python -I shared_cp_live.py        two clients, no mouse and no keyboard (loads go through the patch's mailbox, see olmail.py)

Checks
  SC1  a load on client 0 is followed by client 1 (its log applies the same checkpoint, its hero arrives at the same place)
  SC2  the follower does not send the load back (echo guard: client 1 counts one suppressed echo, client 0 receives nothing back)
  SC3  the other direction: a load on client 1 is followed by client 0
  SC4  twin: with the feature switched off on the receiver (disable bit 2), a load is NOT followed
  SC5  both processes alive
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol, olmail

DISABLE_SHARED_CP = 4
CPS = [("Prison_IsolationCells01_Mid", (1979, 3481)), ("Prison_ToPrisonFloor", (1355, 2298)), ("Prison_PrisonFloor_3rdFloor", (820, 2297))]


def log_mark(c):
    try:
        return len(open(c["log"], encoding="utf-8", errors="replace").read())
    except OSError:
        return 0


def applied_since(c, mark, name, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if f"GS - Applying checkpoint {name}" in open(c["log"], encoding="utf-8", errors="replace").read()[mark:]:
                return True
        except OSError:
            pass
        time.sleep(1)
    return False


def hero(port):
    h = ol.read_state()["heroes"].get(str(port))
    return (round(h["x"]), round(h["y"])) if h else None


def near(p, q, tol=150):
    return bool(p) and abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol


def counters(c):
    d = olmail.read(c["pid"])
    return {k: d.get(k) for k in ("cnt_follow_sent", "cnt_follow_recv", "cnt_follow_exec", "cnt_echo_suppressed")}


def result(name, ok, detail):
    print(f"RESULT {'PASS' if ok else 'FAIL'} {name} {detail}", flush=True)
    return ok


def one_way(leader, follower, cp, at, label):
    m = log_mark(follower)
    code, _ = olmail.send_load(leader["pid"], cp)
    followed = applied_since(follower, m, cp, 60)
    time.sleep(4)
    pos = hero(follower["port"])
    return result(label, code == 0 and followed and near(pos, at), f"leader mailbox {code}, follower applied {followed}, follower hero {pos} (checkpoint at {at})")


def main():
    ol.up()
    ol.launch(2, "prison_persistent")
    cs = ol.clients()
    time.sleep(20)
    a, b = cs
    for c in cs:
        olmail.set_disable(c["pid"], 0)
    one_way(a, b, *CPS[0], "SC1.load-on-A-is-followed-by-B")
    time.sleep(3)
    ca, cb = counters(a), counters(b)
    print("counters A", ca, "B", cb, flush=True)
    result("SC2.no-echo-back", cb.get("cnt_echo_suppressed", 0) >= 1 and ca.get("cnt_follow_recv", 0) == 0,
           f"B suppressed {cb.get('cnt_echo_suppressed')}, A received {ca.get('cnt_follow_recv')}")
    one_way(b, a, *CPS[1], "SC3.load-on-B-is-followed-by-A")
    time.sleep(3)
    olmail.set_disable(b["pid"], DISABLE_SHARED_CP)                      # twin: the receiver ignores the partner's load
    m = log_mark(b)
    olmail.send_load(a["pid"], CPS[2][0])
    followed = applied_since(b, m, CPS[2][0], 25)
    result("SC4.twin-switched-off-receiver-does-not-follow", not followed, f"followed {followed}")
    olmail.set_disable(b["pid"], 0)
    alive = [ol.window_rect(c["pid"]) is not None for c in cs]
    result("SC5.both-clients-alive", all(alive), f"{alive}")
    print("final counters A", counters(a), "B", counters(b), flush=True)
    ol.down()


if __name__ == "__main__":
    main()
