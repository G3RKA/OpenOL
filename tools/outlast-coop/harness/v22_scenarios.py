"""Hands-free scenarios on the OpenOL 2.2.0 test copy (no mouse, no keyboard): processes are started and stopped, logs are read.

  python -I v22_scenarios.py

  H1  two clients connect, one AI owner (the first player), both in the world
  H2  the AI owner's process is killed: the other client becomes the owner and stays alive
  H3  the killed player starts again and rejoins: it is not the owner, the other client still is
  H4  the relay is restarted: both clients reconnect (log) and stay alive
"""
import os, re, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v22

results = []


def check(name, ok, why=""):
    results.append(ok)
    print(f"RESULT {'PASS' if ok else 'FAIL'} {name} {why}".rstrip(), flush=True)


def wait_for(c, pat, mark=0, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        m = re.search(pat, v22.read_log(c["log"])[mark:])
        if m:
            return m
        time.sleep(2)
    return None


def kill(pid):
    subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"], capture_output=True)


def main():
    reg = v22.up(2, "prison_persistent")
    a, b = reg["clients"]
    time.sleep(10)
    owner_a = wait_for(a, r"Enemy AI owner: (\d+) \(was \d+, we are (\d+)\)", 0, 5)
    owner_b = wait_for(b, r"Enemy AI owner: (\d+) \(was \d+, we are (\d+)\)", 0, 5)
    pa = re.search(r"Connected! PlayerID=(\d+)", v22.read_log(a["log"]))
    pb = re.search(r"Connected! PlayerID=(\d+)", v22.read_log(b["log"]))
    check("H1.two-clients-one-owner", bool(pa and pb and owner_a and owner_b and owner_a.group(1) == pa.group(1) and owner_b.group(1) == pa.group(1)),
          f"ids {pa and pa.group(1)} {pb and pb.group(1)}; owner seen by a {owner_a and owner_a.group(1)}, by b {owner_b and owner_b.group(1)}")
    mark_b = len(v22.read_log(b["log"]))
    kill(a["pid"])
    new = wait_for(b, rf"Enemy AI owner: {pb.group(1)} ", mark_b, 60)
    check("H2.owner-leaves-the-other-takes-over", bool(new) and v22.alive(b["pid"]), "client b became the owner" if new else "no new owner in 60 s")
    mark_b = len(v22.read_log(b["log"]))
    a2 = v22.launch_client(0, "prison_persistent")
    reg["clients"][0] = a2
    v22.save(reg)
    time.sleep(10)
    c = re.search(r"Connected! PlayerID=(\d+)", v22.read_log(a2["log"]))
    ow = re.findall(r"Enemy AI owner: (\d+) \(was \d+, we are (\d+)\)", v22.read_log(a2["log"]))
    check("H3.returning-player-is-not-the-owner", bool(c) and bool(ow) and ow[-1][0] == pb.group(1), f"rejoined as {c and c.group(1)}, owner seen {ow[-1] if ow else None}")
    check("H3b.the-other-client-kept-its-ownership", not re.search(rf"Enemy AI owner: (?!{pb.group(1)} )\d+", v22.read_log(b["log"])[mark_b:]), "no change of owner on b")
    marks = [len(v22.read_log(x["log"])) for x in reg["clients"]]
    kill(reg["relay"])
    time.sleep(5)
    reg["relay"] = v22.start_relay()
    v22.save(reg)
    again = [wait_for(x, r"Connected! PlayerID", marks[i], 120) for i, x in enumerate(reg["clients"])]
    check("H4.clients-reconnect-after-a-relay-restart", all(again) and all(v22.alive(x["pid"]) for x in reg["clients"]), f"reconnected {[bool(x) for x in again]}")
    v22.down()
    print(f"SUMMARY {sum(results)}/{len(results)}", flush=True)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
