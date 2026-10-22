"""Checkpoint sweep with the enemy census: load every checkpoint of a group on both clients and check the one-owner invariants from memory.

  python -I sweep.py <Group> [Checkpoint ...]        e.g. sweep.py Admin     (names default to the group's list below)
  python -I sweep.py --list

One launch per group (a checkpoint of another persistent level can crash the engine, see the write-up); a crash is recorded and the pair is restarted.
Per checkpoint, 12 s after both clients applied it, for each client the enemies alive in its own list ("real") and as puppets are read from the game's
memory (census.py) and these are checked:
  double_sim   an enemy is real on BOTH clients (same place, 150 units)            -> the one-owner patch failed
  count_diff   the number of enemies a client sees differs between the clients      -> one machine has an enemy the other lacks
  crash        a process died or the log shows an assertion / fatal error since the load
Results are appended as JSON lines to sweep_<Group>.jsonl and printed as one line per checkpoint.
"""
import json, math, os, re, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol, census

GROUPS = {
    "Admin": "Admin_Gates Admin_Garden Admin_MainHall Admin_Mezzanine Admin_SecurityRoom Admin_WheelChair Admin_Electricity Admin_Basement Admin_PostBasement Admin_Explosion",
    "Courtyard": "Courtyard_Start Courtyard_Soldier1 Courtyard_Soldier2 Courtyard_Chapel Courtyard_Corridor Courtyard_FemaleWard",
}
RADIUS = 150.0


def names_of(group):
    if group in GROUPS:
        return GROUPS[group].split()
    d = os.environ.get("OL_CP_PICS")
    if d:
        return sorted(f[:-4] for f in os.listdir(d) if f.startswith(group + "_") and f.endswith(".jpg"))
    sys.exit(f"no checkpoint list for {group}: set OL_CP_PICS to the res\\checkpoints\\main folder of the OpenOL release")


def alive_pid(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True).stdout      # bytes: the console code page is not UTF-8
    return b"OLGame" in out


def log_marker(c):
    try:
        return len(open(c["log"], encoding="utf-8", errors="replace").read())
    except OSError:
        return 0


def bad_log_lines(c, mark):
    try:
        txt = open(c["log"], encoding="utf-8", errors="replace").read()[mark:]
    except OSError:
        return []
    return [l.strip()[:160] for l in txt.splitlines() if re.search(r"Assertion failed|Fatal error|Critical error|Unhandled exception", l)]


def positions(r):
    own = [(e["x"], e["y"], e["z"]) for e in census.alive_own(r)]
    pup = [(p["actor"]["x"], p["actor"]["y"], p["actor"]["z"]) for p in census.alive_puppets(r)]
    return own, pup


def double_sim(ra, rb):
    a, b = positions(ra)[0], positions(rb)[0]
    return sum(1 for p in a if any(math.dist(p, q) < RADIUS for q in b))


def check(name):
    cs = ol.clients()
    marks = [log_marker(c) for c in cs]
    ok = [ol.cp(i, name) for i in range(len(cs))]
    time.sleep(12)
    res = {"checkpoint": name, "applied": ok}
    if not all(alive_pid(c["pid"]) for c in cs) or any(bad_log_lines(c, m) for c, m in zip(cs, marks)):
        res["crash"] = [alive_pid(c["pid"]) for c in cs]
        res["log"] = [bad_log_lines(c, m)[:2] for c, m in zip(cs, marks)]
        return res
    r = [census.census(c["pid"]) for c in cs]
    res["client"] = [{"own": len(census.alive_own(x)), "puppets": len(census.alive_puppets(x))} for x in r]
    res["double_sim"] = double_sim(r[0], r[1])
    tot = [v["own"] + v["puppets"] for v in res["client"]]
    res["count_diff"] = abs(tot[0] - tot[1])
    return res


def run_group(group, names):
    out = open(os.path.join(HERE, f"sweep_{group}.jsonl"), "a", encoding="utf-8")
    ol.down()
    ol.up()
    ol.launch(2, "prison_persistent")
    for name in names:
        res = check(name)
        out.write(json.dumps(res) + "\n")
        out.flush()
        flag = "CRASH" if "crash" in res else ("DOUBLE_SIM" if res["double_sim"] else ("COUNT_DIFF" if res["count_diff"] else "ok"))
        extra = res.get("client", res.get("log", ""))
        print(f"{group:9s} {name:30s} {flag:10s} applied={res['applied']} {extra}", flush=True)
        if "crash" in res:               # restart the pair and go on with the next checkpoint
            ol.down()
            ol.up()
            ol.launch(2, "prison_persistent")
    ol.down()


if __name__ == "__main__":
    if sys.argv[1:] == ["--list"]:
        for g, v in GROUPS.items():
            print(g, len(v.split()), "checkpoints")
        sys.exit(0)
    group = sys.argv[1]
    run_group(group, sys.argv[2:] or names_of(group))
