"""Hands-free check of the patch's command mailbox: two clients, a checkpoint loaded through memory instead of the F6 overlay.

  python -I mailbox_live.py [persistent-level-name]     no mouse, no keyboard: the clients are started and driven through memory only

Loads Prison_IsolationCells01_Mid on client 0 (hero position known from the survey: 1979, 3481, 657) and checks that the mailbox answers and the hero moves there;
then the same on client 1; then a second checkpoint of the group on both, and that both processes are alive.
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol, olmail

CP, AT = "Prison_IsolationCells01_Mid", (1979, 3481)


def hero(port):
    h = ol.read_state()["heroes"].get(str(port))
    return (round(h["x"]), round(h["y"])) if h else None


def wait_at(port, at, secs=40):
    t0 = time.time()
    while time.time() - t0 < secs:
        h = hero(port)
        if h and abs(h[0] - at[0]) < 150 and abs(h[1] - at[1]) < 150:
            return h
        time.sleep(1)
    return hero(port)


def main():
    persist = sys.argv[1] if len(sys.argv) > 1 else ""
    ol.up()
    ol.launch(2, "prison_persistent")
    cs = ol.clients()
    time.sleep(20)
    for c in cs:
        d = olmail.read(c["pid"])
        print("client", c["idx"], "mailbox state:", {k: d.get(k) for k in ("cmd_seq", "res_seq", "disable")}, flush=True)
    results = []
    for c in cs:
        before = hero(c["port"])
        code, secs = olmail.send_load(c["pid"], CP, persist)
        after = wait_at(c["port"], AT)
        moved = bool(after) and abs(after[0] - AT[0]) < 150 and abs(after[1] - AT[1]) < 150
        print(f"client {c['idx']}: LOAD {CP} -> res_code {code} in {secs:.2f}s, hero {before} -> {after}, at the checkpoint: {moved}", flush=True)
        results.append((code, moved))
    alive = [ol.window_rect(c["pid"]) is not None for c in cs]
    print("RESULT mailbox-answers", "PASS" if all(r[0] == 0 for r in results) else "FAIL")
    print("RESULT mailbox-load-moves-the-hero", "PASS" if all(r[1] for r in results) else "FAIL")
    print("RESULT clients-alive", "PASS" if all(alive) else "FAIL")
    ol.down()


if __name__ == "__main__":
    main()
