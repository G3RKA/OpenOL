"""Assert-based suite for OpenOL co-op. One command, one summary line, no clicking by hand.

  python -I suite.py            run everything
  python -I suite.py P          only group P (relay protocol tests with fake peers, no game, ~1 min)
  python -I suite.py A          only group A (prison map: connection, map-enemy ownership)
  python -I suite.py B          only group B (trigger injection + its twin)
  python -I suite.py C          only group C (player-spawned enemy: damage, death, respawn)
  python -I suite.py H          only group H (bad network: tools/chaos bad_wifi, a 10 s and a 40 s blackout)
  python -I suite.py F          only group F (late join: a second client arrives while the first has a living enemy)
  python -I suite.py E          only group E (relay inside the shipped exe, started from the overlay; edits and restores the ini)
  python -I suite.py D          only group D (SyncEnemies=False workaround; edits and restores OLMultiplayer.ini)

Each test prints  RESULT: PASS | FAIL | XFAIL | XPASS | ERROR  <name> <why>.
  XFAIL = known bug, still failing (documented). XPASS = a known bug got fixed: update the expectation.
Exit code 0 only if there is no FAIL, no ERROR and no XPASS.
Group runs start the relay + proxy, launch two clients on a map (ol.py), load a checkpoint, assert, stop everything.
Mutation twin: the trigger test is also run with a bogus trigger path, which must be scored FAIL (proves the check can fail).
"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol  # noqa: E402

PY = [sys.executable, "-I"]
results = []


def record(status, name, why=""):
    results.append((status, name, why))
    print(f"RESULT: {status} {name} {why}".rstrip(), flush=True)


def log_text(c):
    return open(c["log"], encoding="utf-8", errors="replace").read()


def count(c, pat):
    return len(re.findall(pat, log_text(c)))


def crash_dialogs():
    """Texts of Windows error boxes owned by game processes (UE3 shows one on a crash and stops logging)."""
    import ctypes
    import ctypes.wintypes as wt
    u = ctypes.windll.user32
    out = []
    pids = {c["pid"] for c in ol.clients()}
    P = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(h, _):
        p = wt.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        cls = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(h, cls, 64)
        if p.value in pids and cls.value == "#32770" and u.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(4096)
            kids = []
            ck = P(lambda c, __: (u.GetWindowTextW(c, buf, 4096), kids.append(buf.value[:200]))[0] and True)
            u.EnumChildWindows(h, ck, 0)
            out.append(" ".join(k for k in kids if k)[:200])
        return True

    u.EnumWindows(P(cb), 0)
    return out


def wait_for(cond, timeout, step=1.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = cond()
        if v:
            return v
        time.sleep(step)
    return None


def expect(name, ok, why_pass, why_fail, xfail=False):
    """Score one assertion. xfail=True marks a documented known bug. A game crash dialog overrides everything."""
    dlg = crash_dialogs()
    if dlg:
        record("ERROR", name, "game crash dialog: " + dlg[0])
        raise SystemExit("client crashed: " + dlg[0])
    if ok:
        record("XPASS" if xfail else "PASS", name, why_pass if not xfail else "known bug seems fixed: " + why_pass)
    else:
        record("XFAIL" if xfail else "FAIL", name, why_fail)


def tap_size():
    try:
        return os.path.getsize(ol.tap_log())
    except OSError:
        return 0


def tap_since(offset):
    """Proxy log text written after `offset` bytes."""
    with open(ol.tap_log(), "rb") as f:
        f.seek(offset)
        return f.read().decode("utf-8", errors="replace")


def tap_when(offset, pattern, timeout, step=1.0):
    """Wait until the proxy log written after `offset` matches `pattern`; return that text (or the last text on timeout)."""
    t0 = time.time()
    while True:
        if ol.wait_firewall():
            t0 = time.time()   # the time the owner needed to answer does not count against the timeout
        txt = tap_since(offset)
        if re.search(pattern, txt) or time.time() - t0 > timeout:
            return txt
        time.sleep(step)


def relay_timeouts(text):
    """Player ids that timed out, ignoring the first id (ol.up's HELLO probe joins first and never pings)."""
    ids = re.findall(r"ID=(\d+) joined room", text)
    probe = ids[0] if ids else None
    return [i for i in re.findall(r"ID=(\d+) \('[^']*'\) timed out", text) if i != probe]


def scorer_selftest():
    """The scorer must see FAIL on known-bad input and PASS on known-good input (playbook: test the scorer)."""
    probe_only = ("[t] ID=1000 joined room 'PUBLIC' (1 players)\n"
                  "[t] ID=1000 ('Player1000') timed out\n"
                  "[t] ID=1001 joined room 'PUBLIC' (1 players)\n")
    real_timeout = probe_only + "[t] ID=1001 ('Player') timed out\n"
    ok = relay_timeouts(probe_only) == [] and relay_timeouts(real_timeout) == ["1001"] and relay_timeouts("") == []
    if ok:
        record("PASS", "S0.scorer-selftest", "relay timeout scorer sees good and bad input")
    else:
        record("ERROR", "S0.scorer-selftest", "scorer wrong")


# ---------------------------------------------------------------- group P: relay protocol tests (no game)

def group_p():
    """Runs relay_filter_test.py and relay_state_test.py (fake peers, no game) and records every RESULT line they print."""
    patched = os.environ.get("OL_PATCHED_RELAY_EXE", os.path.join(HERE, "OpenOL_Relay_patched.exe"))
    upstream = os.environ.get("OL_UPSTREAM_RELAY_EXE", os.path.join(HERE, "OpenOL_Relay.exe"))
    if not (os.path.exists(patched) and os.path.exists(upstream)):
        record("SKIP", "P.relay-protocol-tests", f"need a patched and an upstream relay exe ({patched}, {upstream})")
        return
    for script, exes in (("relay_filter_test.py", [patched, upstream]), ("relay_state_test.py", [patched])):
        r = subprocess.run(PY + [os.path.join(HERE, script), *exes], capture_output=True, text=True, timeout=240)
        lines = re.findall(r"^RESULT: (PASS|FAIL) (\S+) ?(.*)$", r.stdout, re.M)
        if not lines:
            record("ERROR", f"P.{script}", "no RESULT lines: " + " ".join((r.stderr or r.stdout)[-160:].split()))
        for status, name, why in lines:
            record(status, f"P.{name}", why)
    # The late-join snapshot tests (S9 to S12) are the known upstream bug that patch 0003 fixes: the upstream CLI relay never sends the queue.
    r = subprocess.run(PY + [os.path.join(HERE, "relay_state_test.py"), upstream], capture_output=True, text=True, timeout=240)
    for status, name, why in re.findall(r"^RESULT: (PASS|FAIL) (\S+) ?(.*)$", r.stdout, re.M):
        if re.match(r"S(9|10|11)\.", name):
            record("XFAIL" if status == "FAIL" else "XPASS", f"P.upstream.{name}", why)


def _native_patch():
    """True when the game exe under test carries the one-owner patch (section .olfix); then A4/A4b must pass instead of being a known bug."""
    try:
        return b".olfix" in open(os.path.join(ol.GAME, "OLGame.exe"), "rb").read(2048)
    except OSError:
        return False


NATIVE_PATCH = _native_patch()


# ---------------------------------------------------------------- group A: prison map

def group_a():
    ol.up()
    ol.launch(2, "prison_persistent")
    cs = ol.clients()
    # A1: both clients joined once, the same player ids for a while (the 30 s reconnect loop would break this)
    time.sleep(45)
    s = ol.read_state()
    fresh = [c for c in cs if (h := s["heroes"].get(str(c["port"]))) and time.time() - h["t"] < 3]
    expect("A1.both-clients-send-state", len(fresh) == 2, "2 of 2 clients fresh", f"{len(fresh)} of 2 fresh")
    joins = [count(c, r"MpConn: Connected!") for c in cs]
    expect("A2.no-reconnect-in-45s", all(j == 1 for j in joins), f"Connected! counts {joins}",
           f"Connected! counts {joins} (reconnect loop?)")
    # A3: the relay must not time out a real client (the first id is the HELLO probe from ol.up, which never pings)
    # ol.py up writes relay_<hhmmss>.log next to the relay exe (or next to ol.py); take the newest of either place
    cands = []
    for d in (HERE, os.path.dirname(os.environ.get("OL_RELAY_EXE", "")) or HERE):
        if os.path.isdir(d):
            cands += [os.path.join(d, f) for f in os.listdir(d) if re.fullmatch(r"relay_\d{6}\.log", f)]
    rlogs = sorted(set(cands), key=os.path.getmtime)
    rl = open(rlogs[-1], encoding="utf-8", errors="replace").read() if rlogs else ""
    bad = relay_timeouts(rl)
    expect("A3.relay-no-timeouts-of-real-clients", rlogs and not bad, "no real client timed out",
           f"timed out: {bad}" if rlogs else "no relay log found")
    # A6/A7: doors. A scripted peer opens a real door (taken from the doors the clients announced); a real client applying it
    # echoes the packet back once (seen in proxy), so both clients must echo. Twin: a position with no door must not echo.
    st = ol.read_state()
    h0 = st["heroes"].get(str(cs[0]["port"]))
    doors = [tuple(int(v) for v in k.split(",")) for k in st["doors"]]
    if doors and h0:
        d = min(doors, key=lambda k: (k[0] - h0["x"]) ** 2 + (k[1] - h0["y"]) ** 2)
        ports = [str(c["port"]) for c in cs]
        for name, pos, should in (("A6.injected-door-open-applied-by-both", d, True),
                                  ("A7.twin-bogus-door-position-not-applied", (d[0] + 7777, d[1] + 7777, d[2]), False)):
            off = tap_size()
            subprocess.run(PY + [os.path.join(HERE, "fake_peer.py"), "127.0.0.1", "17778", "PUBLIC", "door", "open", *map(str, pos)],
                           capture_output=True, text=True, timeout=60)
            time.sleep(4)
            txt = tap_since(off)
            echoed = [p for p in ports if re.search(rf"C>R {p} DOOR OPEN pos=\({pos[0]},{pos[1]},{pos[2]}\)", txt)]
            if should:
                expect(name, len(echoed) == 2, f"both clients applied the door at {pos}", f"echoed by {len(echoed)} of 2 clients at {pos}")
            else:
                expect(name, not echoed, "nothing applied", f"clients {echoed} applied a door that does not exist")
    else:
        record("ERROR", "A6.injected-door-open-applied-by-both", "no door announced by the clients")
    # A4: map enemies must have ONE owner. Without the native patch (nativepatch/olfix.c) each client simulates its own copy (known bug).
    for i in range(len(cs)):
        ol.cp(i, "Prison_OldCells_PreStruggle2")
    time.sleep(8)
    s = ol.read_state()
    owners = {}
    for name, e in s["enemies"].items():
        if "Patient" not in name:
            continue
        for k, p in e.items():
            if k.startswith("C>R") and not k.endswith((" mode", " t", " look")) and time.time() - e.get(k + " t", 0) < 5:
                owners.setdefault(tuple(round(v / 50) for v in p), set()).add(k.split()[1])
    dup = [pos for pos, o in owners.items() if len(o) > 1]
    expect("A4.map-enemy-has-one-owner", not dup, f"{len(owners)} patient spot(s), one sender each",
           f"{len(dup)} spot(s) with patients sent by both clients", xfail=not NATIVE_PATCH)
    # A5: both players spawn together (sanity of the checkpoint load itself)
    h = [s["heroes"].get(str(c["port"])) for c in cs]
    near = all(h) and abs(h[0]["x"] - h[1]["x"]) < 30 and abs(h[0]["y"] - h[1]["y"]) < 30
    expect("A5.checkpoint-spawns-both-together", near, "both heroes at the same point", f"heroes at {[(x['x'], x['y']) if x else None for x in h]}")
    # A4b: the same with the load order reversed (the higher player id loads first), another checkpoint with patients
    for i in reversed(range(len(cs))):
        ol.cp(i, "Prison_OldCells_PreStruggle")
    time.sleep(10)
    s = ol.read_state()
    owners = {}
    for name, e in s["enemies"].items():
        if "Patient" not in name:
            continue
        for k, p in e.items():
            if k.startswith("C>R") and not k.endswith((" mode", " t", " look")) and time.time() - e.get(k + " t", 0) < 5:
                owners.setdefault(tuple(round(v / 50) for v in p), set()).add(k.split()[1])
    dup = [pos for pos, o in owners.items() if len(o) > 1]
    expect("A4b.one-owner-when-the-higher-id-loads-first", not dup and bool(owners), f"{len(owners)} patient spot(s), one sender each",
           f"{len(dup)} spot(s) with patients sent by both clients" if owners else "no patient seen", xfail=not NATIVE_PATCH)
    alive = [subprocess.run(["tasklist", "/FI", f"PID eq {c['pid']}"], capture_output=True, text=True).stdout.count("OLGame") for c in cs]
    expect("A4c.both-clients-still-running", all(alive), "both game processes alive after the enemy handover", f"processes alive: {alive}")
    ol.down()


# ---------------------------------------------------------------- group C: enemies spawned by a player, damage, death, respawn

def group_c():
    ol.up()
    ol.launch(2, "prison_persistent")
    cs = ol.clients()
    A, B = str(cs[0]["port"]), str(cs[1]["port"])
    for i in range(2):
        ol.cp(i, "Admin_MainHall")
    time.sleep(5)
    ol.maxhp(0, 40)   # one hit (51 damage) must be enough to kill either player
    ol.maxhp(1, 40)
    time.sleep(3)
    # C0 control: without an enemy nobody loses health
    off = tap_size()
    time.sleep(8)
    txt = tap_since(off)
    drops = re.findall(r"HERO pid \d+ hp (\d+)->(\d+) smove 0->0", txt)
    hurt = [d for d in drops if int(d[1]) < int(d[0])]
    expect("C0.control-no-enemy-no-damage", not hurt, "no hp loss in 8 s without an enemy", f"hp dropped without an enemy: {hurt[:3]}")
    # C1: an enemy spawned from the overlay at the owner's feet is mirrored on the other client
    off = tap_size()
    ol.spawn(0)
    for _ in range(4):  # an idle enemy next to a motionless player notices the player once it moves (seen by hand)
        if re.search(r"ENEMY \S+ mode 0->2", tap_since(off)):
            break
        time.sleep(3)
        ol.nudge(0)
    txt = tap_when(off, rf"R>C {B} ENEMY 0x01 SPAWN OLEnemy\w+", 20)
    sent = re.findall(rf"C>R {A} ENEMY 0x01 SPAWN (OLEnemy\w+)", txt)
    got = re.findall(rf"R>C {B} ENEMY 0x01 SPAWN (OLEnemy\w+)", txt)
    expect("C1.spawn-mirrored-on-other-client", bool(sent) and set(sent) <= set(got), f"{sent} sent by A and relayed to B",
           f"sent by A {sent}, relayed to B {got}")
    name = sent[0] if sent else None
    # C2: the enemy attacks (somebody takes damage) and C3: a death is announced to the other client
    t_end = time.time() + 60
    k = 0
    while time.time() < t_end and "LIFECYCLE DIED" not in tap_since(off):
        time.sleep(4)
        ol.nudge(k % 2, 0.35, forward=(k // 2) % 2 == 0)  # alternate players and directions: an idle enemy notices movement
        k += 1
    txt = tap_since(off)
    drops = re.findall(r"C>R (\d+) HERO pid \d+ hp (\d+)->(\d+) smove", txt)
    lost = [d for d in drops if int(d[2]) < int(d[1])]
    expect("C2.enemy-damages-a-player", bool(lost), f"hp loss seen, e.g. {lost[:1]}", "nobody lost health within 60 s")
    died = re.findall(r"C>R (\d+) HERO 0x08 LIFECYCLE DIED", txt)
    relayed = [p for p in re.findall(r"R>C (\d+) HERO 0x08 LIFECYCLE DIED", txt)]
    victim = died[0] if died else None
    other = B if victim == A else A
    expect("C3.death-announced-to-other-client", bool(died) and other in relayed, f"client {victim} died, relayed to {other}",
           f"DIED sent by {died}, relayed to {relayed}")
    # C4: the dead player respawns with health again
    txt2 = tap_when(off, "LIFECYCLE RESPAWNED", 30, 2.0)
    time.sleep(5)
    st = ol.read_state()
    hv = st["heroes"].get(victim) if victim else None
    expect("C4.respawn-with-health", "LIFECYCLE RESPAWNED" in txt2 and hv and hv["hp"] >= 30,
           f"respawned, hp {hv['hp'] if hv else '?'}", f"respawn announced: {'LIFECYCLE RESPAWNED' in txt2}, hp {hv['hp'] if hv else '?'}")
    # Keep the enemy alive and moving the players until the OWNER (A) has died too, so both directions get checked.
    t_end = time.time() + 90
    k = 0
    while time.time() < t_end and A not in re.findall(r"C>R (\d+) HERO 0x08 LIFECYCLE DIED", tap_since(off)):
        time.sleep(4)
        ol.nudge(k % 2, 0.35, forward=(k // 2) % 2 == 0)
        k += 1
    txt = tap_since(off)

    def when(pattern):
        """(seconds-of-day, groups) for every proxy line matching `pattern` (the line starts with HH:MM:SS)."""
        out = []
        for m in re.finditer(r"^(\d\d):(\d\d):(\d\d) " + pattern, txt, re.M):
            out.append((int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)), m.groups()[3:]))
        return out

    died_at = {p[0]: t for t, p in when(r"C>R (\d+) HERO 0x08 LIFECYCLE DIED")}
    dels = [(t, p[0], p[1]) for t, p in when(r"C>R (\d+) ENEMY 0x02 DEL (OLEnemy\w+)")]
    owners = {p[1]: p[0] for _, p in when(r"C>R (\d+) ENEMY 0x01 SPAWN (OLEnemy\w+)")}
    wrong = [(p, n) for _, p, n in dels if owners.get(n) != p]
    # C5: the owner's death deletes the owner's enemy (for everyone: the relay forwards the DEL to the other client)
    if A in died_at:
        gone = [t for t, p, n in dels if n == name and p == A and t >= died_at[A] - 1]
        expect("C5.owner-death-deletes-its-enemy", bool(gone) and not wrong, f"{name} deleted by its owner at its death",
               f"DEL lines {dels}, owners {owners}")
    else:
        record("SKIP", "C5.owner-death-deletes-its-enemy", "the owner did not die within 90 s")
    # C6: a non-owner's death must not delete the owner's enemy; it is deleted only when the owner dies
    if B in died_at:
        early = [t for t, p, n in dels if n == name and t < died_at.get(A, 10 ** 9) - 1]
        expect("C6.non-owner-death-keeps-the-owners-enemy", not early and not wrong, f"{name} stayed after {B} died",
               f"{name} deleted at {early} before the owner died; DEL lines {dels}")
    else:
        record("SKIP", "C6.non-owner-death-keeps-the-owners-enemy", "the non-owner did not die")
    ol.down()


# ---------------------------------------------------------------- group D: SyncEnemies=False (no-source workaround for duplicated map enemies)

class IniOverride:
    """Temporarily set keys in the test copy's OLMultiplayer.ini (clients read it when they start); always restores the file."""

    def __init__(self, **kv):
        self.kv = kv
        self.path = os.path.normpath(os.path.join(ol.GAME, "..", "..", "OLGame", "Config", "OLMultiplayer.ini"))

    def __enter__(self):
        self.old = open(self.path, encoding="utf-8").read()
        text = self.old
        for k, v in self.kv.items():
            text, n = re.subn(rf"^{k}=.*$", f"{k}={v}", text, flags=re.M)
            if not n:
                raise SystemExit(f"{k} not found in {self.path}")
        open(self.path, "w", encoding="utf-8").write(text)
        return self

    def __exit__(self, *exc):
        open(self.path, "w", encoding="utf-8").write(self.old)


def group_d():
    with IniOverride(SyncEnemies="False"):
        ol.up()
        ol.launch(2, "prison_persistent")
        cs = ol.clients()
        A, B = str(cs[0]["port"]), str(cs[1]["port"])
        for i in range(2):
            ol.cp(i, "Prison_OldCells_PreStruggle2")   # a map patient 956 units away, present on both clients
        time.sleep(10)
        off = tap_size()
        time.sleep(10)
        txt = tap_since(off)
        n_enemy = len(re.findall(r"ENEMY 0x0[1-8]|ENEMY \S+ mode", txt))
        expect("D1.no-enemy-packets-cross-the-relay", n_enemy == 0, "no ENEMY packet in 10 s", f"{n_enemy} enemy lines")
        # every client still has its own map patient (they are simply not shared): the log shows the map enemy's checkpoint load
        for c, who in ((cs[0], "A"), (cs[1], "B")):
            expect(f"D2.{who}-keeps-its-own-map-enemy", count(c, r"Applying checkpoint Prison_OldCells_PreStruggle2") >= 1,
                   "checkpoint with the patient applied", "checkpoint not applied")
        # D3-D5 need a place where a spawned Soldier really attacks (not the prison corridors): the main hall
        for i in range(2):
            ol.cp(i, "Admin_MainHall")
        time.sleep(5)
        # D3: an enemy spawned by A attacks A only; no damage event for B is relayed (SendPlayerHit is gated by SyncEnemies)
        ol.maxhp(0, 40)
        ol.maxhp(1, 40)
        time.sleep(3)
        off = tap_size()
        ol.spawn(0)
        atk0 = count(cs[0], r"SMT_AttackGrab")
        t_end = time.time() + 90
        k = 0
        while time.time() < t_end and count(cs[0], r"SMT_AttackGrab") <= atk0:
            time.sleep(4)
            ol.nudge(0, 0.35, forward=(k % 2 == 0))
            k += 1
        time.sleep(5)
        txt = tap_since(off)
        sp = re.findall(r"ENEMY 0x01 SPAWN", txt)
        expect("D3.a-spawned-enemy-is-not-mirrored", not sp, "no SPAWN packet relayed", f"{len(sp)} SPAWN packets")
        lost = [m for m in re.findall(r"C>R (\d+) HERO pid \d+ hp (\d+)->(\d+) smove", txt) if int(m[2]) < int(m[1])]
        # precondition of D3/D4 (they would pass vacuously without an attack): the enemy on A's client really attacked
        expect("D5.precondition-the-local-enemy-attacked", count(cs[0], r"SMT_AttackGrab") > atk0, "SMT_AttackGrab in A's log",
               "the enemy never attacked within 90 s, D3/D4 prove nothing")
        # the other player is not hurt: the enemy exists only on A's client (B sits at the same spot)
        expect("D4.the-other-player-takes-no-damage", not any(m[0] == B for m in lost), "B lost no health",
               f"B lost health: {[m for m in lost if m[0] == B][:2]}")
        ol.down()


# ---------------------------------------------------------------- group E: the relay built into the shipped OLGame.exe ("Start Server")

def group_e():
    """Two real clients on the relay that a client starts itself from the F6 overlay (the code path of the Multiplayer menu's Start Server).
    It only has room DEFAULT, so the test copy's RoomCode is switched for the run (restored afterwards)."""
    with IniOverride(RoomCode="DEFAULT"):
        ol.up(relay=False, target_port=17780)
        ol.launch(2, "prison_persistent")
        cs = ol.clients()
        ol.embedded_relay(0, 17780)
        got = wait_for(lambda: all(count(c, r"MpConn: Connected!") >= 1 for c in cs), 60)
        expect("E1.both-clients-join-the-embedded-relay", bool(got), "both clients Connected!",
               f"Connected! counts {[count(c, r'MpConn: Connected!') for c in cs]}")
        time.sleep(65)
        joins = [count(c, r"MpConn: Connected!") for c in cs]
        expect("E2.no-reconnect-in-65s", all(j == 1 for j in joins), f"Connected! counts {joins}", f"Connected! counts {joins} (reconnect loop?)")
        st = ol.read_state()
        fresh = [c for c in cs if (h := st["heroes"].get(str(c["port"]))) and time.time() - h["t"] < 3]
        expect("E3.both-heroes-stream-state", len(fresh) == 2, "2 of 2 heroes fresh", f"{len(fresh)} of 2 fresh")
        r = subprocess.run(PY + [os.path.join(HERE, "embedded_probe.py"), "17780"], capture_output=True, text=True, timeout=60)
        types = set(int(t) for t in re.findall(r"\d+", r.stdout.split("TYPES", 1)[1])) if "TYPES" in r.stdout else set()
        expect("E4.late-join-snapshot-has-spawn", 1 in types, f"types {sorted(types)}", f"types {sorted(types)}")
        expect("E5.late-join-snapshot-has-enemy-position", 4 in types, f"types {sorted(types)}",
               f"snapshot types {sorted(types)}: no LOC (the shipped relay stores ENEMY_LOC as 0x08, the client sends 0x04)", xfail=True)
        m = re.search(r"AUTO (\d)", r.stdout)
        expect("E6.late-joiner-gets-the-pickup-snapshot-unasked", bool(m) and m.group(1) == "1", "pickup state replayed to the late joiner",
               f"no pickup replay ({r.stdout.strip()[-80:]!r}): the shipped relay's snapshot queue is not sent either")
        ol.down()


# ---------------------------------------------------------------- group F: late join with a live enemy (real clients)

def group_f():
    """A second client joins (and loads the same checkpoint) after the first one already has a living enemy: it must get a dummy of it."""
    ol.up()
    ol.launch(1, "prison_persistent")
    A = str(ol.clients()[0]["port"])
    ol.cp(0, "Admin_MainHall")
    time.sleep(5)
    off = tap_size()
    ol.spawn(0, attack=False)           # a calm enemy: an attacking one could kill the owner and delete itself before the late joiner arrives
    txt = tap_when(off, rf"C>R {A} ENEMY 0x01 SPAWN OLEnemy\w+", 20)
    names = re.findall(rf"C>R {A} ENEMY 0x01 SPAWN (OLEnemy\w+)", txt)
    if not names:
        record("ERROR", "F0.precondition-enemy-spawned", "A's enemy never appeared")
        ol.down()
        return
    name = names[0]
    off = tap_size()
    ol.launch(1, "prison_persistent", append=True)     # the late joiner
    B = str(ol.clients()[1]["port"])
    ol.cp(1, "Admin_MainHall")
    txt = tap_when(off, rf"R>C {B} ENEMY 0x01 SPAWN {name}", 40)
    expect("F1.late-joiner-gets-the-existing-enemy", bool(re.search(rf"R>C {B} ENEMY 0x01 SPAWN {name}", txt)), f"{name} relayed to the late joiner",
           f"no SPAWN of {name} reached the late joiner")
    time.sleep(8)
    st = ol.read_state()
    e = st["enemies"].get(name, {})
    expect("F2.late-joiner-gets-its-position", f"R>C {B}" in e and time.time() - e.get(f"R>C {B} t", 0) < 10 if f"R>C {B} t" in e else f"R>C {B}" in e,
           f"position {e.get(f'R>C {B}')}", f"no position for {name} at the late joiner ({sorted(e)})")
    h = st["heroes"].get(B)
    expect("F3.late-joiner-streams-its-state", bool(h) and time.time() - h["t"] < 3, "fresh hero state", "no fresh hero state from the late joiner")
    ca = count(ol.clients()[0], r"MpConn: Connected!")
    expect("F4.the-first-client-is-not-disturbed", ca == 1, "A still on its first connection", f"A Connected! count {ca}")
    ol.down()


# ---------------------------------------------------------------- group N: the native patch keeps a real map enemy playable

def group_n():
    """With the one-owner patch, a real (map-placed) enemy must stay playable: one owner, it can hurt a player, both clients survive, and the
    story can go on (a later checkpoint loads on both). Meaningful only on the patched exe; skipped on the original."""
    if not NATIVE_PATCH:
        record("SKIP", "N.native-patch-not-present", "the game exe has no .olfix section; run on the patched exe")
        return
    ol.up()
    ol.launch(2, "prison_persistent")
    cs = ol.clients()
    ports = [str(c["port"]) for c in cs]
    for i in range(2):
        ol.cp(i, "Prison_OldCells_PreStruggle2")
    time.sleep(10)
    s = ol.read_state()
    # N1: exactly one owner per patient spot (the patch result, on a real map enemy)
    owners = {}
    for name, e in s["enemies"].items():
        if "Patient" not in name:
            continue
        for k in e:
            if k.startswith("C>R") and not k.endswith((" mode", " t", " look")) and time.time() - e.get(k + " t", 0) < 6:
                owners.setdefault(name, set()).add(k.split()[1])
    dup = {n: o for n, o in owners.items() if len(o) > 1}
    expect("N1.real-map-enemy-one-owner", bool(owners) and not dup, f"{len(owners)} patient(s), one sender each",
           f"patients with two senders: {dup}" if owners else "no map patient streamed (checkpoint has none?)")
    # N2: both game processes are still alive after the dedupe handover
    alive = [subprocess.run(["tasklist", "/FI", f"PID eq {c['pid']}"], capture_output=True, text=True).stdout.count("OLGame") for c in cs]
    expect("N2.both-clients-alive", all(alive), "both processes alive", f"alive: {alive}")
    # N3: the story can still advance - load the next checkpoint in the same group on both, both heroes arrive together
    for i in range(2):
        ol.cp(i, "Prison_Showers_Exit")
    time.sleep(8)
    s = ol.read_state()
    h = [s["heroes"].get(p) for p in ports]
    moved = all(x and time.time() - x["t"] < 4 for x in h)
    near = moved and abs(h[0]["x"] - h[1]["x"]) < 40 and abs(h[0]["y"] - h[1]["y"]) < 40
    expect("N3.story-advances-after-dedupe", near, "both heroes at the next checkpoint, streaming",
           f"heroes {[(round(x['x']), round(x['y'])) if x else None for x in h]}")
    alive = [subprocess.run(["tasklist", "/FI", f"PID eq {c['pid']}"], capture_output=True, text=True).stdout.count("OLGame") for c in cs]
    expect("N4.both-clients-alive-after-a-second-load", all(alive), "both processes alive after another load", f"alive: {alive}")
    ol.down()


# ---------------------------------------------------------------- group G: the real player path (menu, New Game, rejoin) -- needs real mouse and keyboard

def group_g():
    """Both clients are started at the main menu, connect through Multiplayer > Connect (ini values), start New Game and play the intro: the car-ride
    cutscene crosses the relay, the story saves Admin_Gates on both; then one client is killed and rejoins through the menu."""
    import ol_menu
    ol.up()
    reg = []
    for i in range(2):
        c = ol_menu.launch_menu(i)
        reg.append(c)
        ol_menu.connect(c)
    ol.save(reg)
    ports = [str(c["port"]) for c in reg]
    expect("G1.both-connect-through-the-menu", all(count(c, r"MpConn: Connected!") == 1 for c in reg), "one Connected! per client", "a client did not connect exactly once")
    for c in reg:
        ol_menu.new_game(c)
    deadline = time.time() + 240
    while time.time() < deadline and not all(count(c, r'SAVING CHECKPOINT "Admin_Gates"') >= 1 for c in reg):
        time.sleep(5)
    expect("G2.new-game-reaches-the-first-checkpoint-on-both", all(count(c, r'Starting at checkpoint "StartGame"') >= 1 and count(c, r'SAVING CHECKPOINT "Admin_Gates"') >= 1 for c in reg),
           "StartGame then Admin_Gates on both clients", f"checkpoint lines: {[count(c, r'SAVING CHECKPOINT') for c in reg]}")
    st = ol.read_state()
    mats = st.get("matinees", {})
    both_ways = any(all(any(k.startswith(d) and p in k for k in v) for p in ports for d in ("C>R", "R>C")) for v in mats.values())
    expect("G3.car-ride-cutscene-crosses-the-relay-both-ways", both_ways, "a matinee seen in both directions for both clients", f"matinees: {list(mats)}")
    h = [st["heroes"].get(p) for p in ports]
    expect("G4.heroes-stream-and-share-the-start-point", all(x and time.time() - x["t"] < 4 for x in h) and abs(h[0]["x"] - h[1]["x"]) < 60 and abs(h[0]["y"] - h[1]["y"]) < 60,
           "both streaming at one place", f"heroes {[(round(x['x']), round(x['y'])) if x else None for x in h]}")
    # rejoin: kill client 1, start it again at the menu and connect
    subprocess.run(["taskkill", "/F", "/PID", str(reg[1]["pid"])], capture_output=True)
    time.sleep(5)
    c2 = ol_menu.launch_menu(1)
    ol_menu.connect(c2)
    reg[1] = c2
    ol.save(reg)
    time.sleep(10)
    st = ol.read_state()
    h0, h1 = st["heroes"].get(ports[0]), st["heroes"].get(str(c2["port"]))
    expect("G5.a-killed-client-rejoins-through-the-menu", count(c2, r"MpConn: Connected!") == 1 and bool(h1) and time.time() - h1["t"] < 5 and bool(h0) and time.time() - h0["t"] < 5,
           "rejoined, both streaming", f"rejoin Connected! {count(c2, r'MpConn: Connected!')}, hero A fresh {bool(h0)}, hero B fresh {bool(h1)}")
    ol.down()


# ---------------------------------------------------------------- group H: bad network (tools/chaos between the proxy and the relay)

def group_h():
    """Two real clients behind an impaired link ('bad_wifi': ~35 ms +/- 25, 2% loss with bursts, reordering). Then a 10 s and a 40 s blackout."""
    ol.up(chaos="bad_wifi")
    ol.launch(2, "prison_persistent")
    cs = ol.clients()
    ports = [str(c["port"]) for c in cs]
    time.sleep(90)
    joins = [count(c, r"MpConn: Connected!") for c in cs]
    expect("H1.connection-survives-90s-of-bad-wifi", all(j == 1 for j in joins), f"Connected! counts {joins}",
           f"Connected! counts {joins} (a reconnect under 2% loss?)")

    def fresh_count():
        st = ol.read_state()
        return sum(1 for c in cs if (h := st["heroes"].get(str(c["port"]))) and time.time() - h["t"] < 3)

    expect("H2.both-heroes-still-stream", fresh_count() == 2, "2 of 2 fresh", f"{fresh_count()} of 2 fresh")
    # H3: a door sequence: 10 alternating DOOR_OPEN/CLOSE (1 s apart) must be applied by both clients at least 7 times (each applied change is echoed once)
    st = ol.read_state()
    h0 = st["heroes"].get(ports[0])
    doors = [tuple(int(v) for v in k.split(",")) for k in st["doors"]]
    if doors and h0:
        d = min(doors, key=lambda k: (k[0] - h0["x"]) ** 2 + (k[1] - h0["y"]) ** 2)
        off = tap_size()
        subprocess.run(PY + [os.path.join(HERE, "fake_peer.py"), "127.0.0.1", "17778", "PUBLIC", "doors-burst", *map(str, d), "10", "1.0"],
                       capture_output=True, text=True, timeout=120)
        time.sleep(3)
        txt = tap_since(off)
        echoes = [len(re.findall(rf"C>R {p} DOOR (?:OPEN|CLOSE) pos=\({d[0]},{d[1]},{d[2]}\)", txt)) for p in ports]
        expect("H3.door-sequence-mostly-applied-under-loss", all(e >= 7 for e in echoes), f"echoes per client {echoes} of 10", f"echoes per client {echoes} of 10")
    else:
        record("ERROR", "H3.door-sequence-mostly-applied-under-loss", "no door known")
    # H4: a 10 s blackout (shorter than the 30 s timeout) must not cause a reconnect and the streams must resume
    ol.chaos_call("disconnect", '{"duration_ms": 10000}')
    time.sleep(20)
    joins = [count(c, r"MpConn: Connected!") for c in cs]
    expect("H4.a-10s-blackout-causes-no-reconnect", all(j == 1 for j in joins) and fresh_count() == 2,
           f"Connected! counts {joins}, streams resumed", f"Connected! counts {joins}, fresh {fresh_count()}")
    # H5: a 40 s blackout (longer than the 30 s timeout) drops the connection; the clients must reconnect on their own and stream again
    ol.chaos_call("disconnect", '{"duration_ms": 40000}')
    time.sleep(55)
    t_end = time.time() + 40
    while time.time() < t_end and not (all(count(c, r"MpConn: Connected!") >= 2 for c in cs) and fresh_count() == 2):
        time.sleep(3)
    joins = [count(c, r"MpConn: Connected!") for c in cs]
    expect("H5.a-40s-blackout-is-recovered-by-reconnecting", all(j >= 2 for j in joins) and fresh_count() == 2,
           f"Connected! counts {joins}, streams resumed", f"Connected! counts {joins}, fresh {fresh_count()}")
    ol.down()


# ---------------------------------------------------------------- group B: adminblock map

def inject(path):
    r = subprocess.run(PY + [os.path.join(HERE, "fake_peer.py"), "127.0.0.1", "17778", "PUBLIC", "trigger", path],
                       capture_output=True, text=True, timeout=60)
    return r.returncode == 0


def trigger_case(name, path, marker, should_fire):
    cs = ol.clients()
    before = [count(c, re.escape(marker)) for c in cs]
    ok = inject(path)
    if not ok:
        record("ERROR", name, "fake_peer failed to send")
        return
    time.sleep(4)
    after = [count(c, re.escape(marker)) for c in cs]
    fired = [a - b for a, b in zip(after, before)]
    if should_fire:
        expect(name, all(f >= 1 for f in fired), f"fired on both clients {fired}", f"fire counts {fired}")
    else:
        # mutation twin: a bogus path must NOT fire; the SCORE of the check is FAIL when something fired
        expect(name, all(f == 0 for f in fired), f"nothing fired {fired}", f"fired {fired}")


def trigger_at(path, pos):
    """A scripted peer stands at pos (a real hero packet from the proxy state is reused), then sends one trigger."""
    st = os.path.join(HERE, "state.json")
    r = subprocess.run(PY + [os.path.join(HERE, "fake_peer.py"), "127.0.0.1", "17778", "PUBLIC", "trigger-at", path,
                             *map(str, pos), st], capture_output=True, text=True, timeout=60)
    return r.returncode == 0


def group_b():
    # The trigger interest filter lives in the patched relay (--trigger-radius); without it B3 is the known upstream bug.
    patched = os.environ.get("OL_PATCHED_RELAY_EXE", os.path.join(HERE, "OpenOL_Relay_patched.exe"))
    use_patch = os.path.exists(patched)
    old = {k: os.environ.get(k) for k in ("OL_RELAY_EXE", "OL_RELAY_ARGS")}
    if use_patch:
        os.environ["OL_RELAY_EXE"] = patched
        os.environ["OL_RELAY_ARGS"] = "--trigger-radius 3000"
    try:
        ol.up()
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    ol.launch(2, "prison_persistent")  # adminblock_persistent as a start map crashes (UnWorld.cpp:1693); jump by checkpoint
    for i in range(len(ol.clients())):
        ol.cp(i, "Admin_Explosion")
    time.sleep(5)
    good = "center_block_sript.TheWorld:PersistentLevel.Main_Sequence.SeqEvent_Touch_3"
    bogus = "center_block_sript.TheWorld:PersistentLevel.Main_Sequence.SeqEvent_Touch_999"
    trigger_case("B1.injected-trigger-fires-on-both", good, "ForceActivateTouchEvent: SeqEvent_Touch_3 ", True)
    trigger_case("B2.twin-bogus-trigger-does-not-fire", bogus, "ForceActivateTouchEvent: SeqEvent_Touch_999", False)
    # B3/B4: the same trigger sent by a peer that stands far away (B3, first) or at the players' position (B4, control).
    # The trigger must be repeatable (MaxTriggerCount=0): a one-shot trigger used up by B3/B4 would make the second case meaningless.
    cs = ol.clients()
    h = ol.read_state()["heroes"].get(str(cs[0]["port"]))
    foreign = good
    marker = "ForceActivateTouchEvent: SeqEvent_Touch_3 "
    time.sleep(8)  # let the Kismet chain of B1 finish (repeatable triggers are dropped while their chain is playing)
    for name, pos, should_fire, xfail in (
            ("B3.trigger-from-a-far-away-peer-is-not-applied", (h["x"] + 50000, h["y"], h["z"]), False, not use_patch),
            ("B4.control-trigger-from-a-peer-next-to-the-players-fires", (h["x"], h["y"], h["z"]), True, False)):
        before = [count(c, marker) for c in cs]
        if not trigger_at(foreign, pos):
            record("ERROR", name, "fake_peer failed")
            continue
        time.sleep(4)
        fired = [count(c, marker) - b for c, b in zip(cs, before)]
        if should_fire:
            expect(name, all(f >= 1 for f in fired), f"fired on both clients {fired}", f"fire counts {fired}")
        else:
            expect(name, all(f == 0 for f in fired), f"ignored {fired}" + (" (patched relay)" if use_patch else ""),
                   f"a far-away peer's trigger fired on clients {fired}" + ("" if use_patch else " (upstream relay, known bug)"), xfail=xfail)
    ol.down()


def main():
    which = sys.argv[1].upper() if len(sys.argv) > 1 else "PABCDEFH"
    t0 = time.time()
    try:
        scorer_selftest()
        if "P" in which:
            group_p()
        if "A" in which:
            group_a()
        if "B" in which:
            group_b()
        if "C" in which:
            group_c()
        if "D" in which:
            group_d()
        if "E" in which:
            group_e()
        if "F" in which:
            group_f()
        if "N" in which:
            group_n()
        if "G" in which:
            group_g()
        if "H" in which:
            group_h()
    except SystemExit as e:
        record("ERROR", "suite", f"aborted: {e}")
    except Exception as e:  # noqa: BLE001 - the runner must always print a summary
        record("ERROR", "suite", f"{type(e).__name__}: {e}")
    finally:
        try:
            ol.down()
        except Exception:  # noqa: BLE001
            pass
    counts = {}
    for s, _, _ in results:
        counts[s] = counts.get(s, 0) + 1
    bad = counts.get("FAIL", 0) + counts.get("ERROR", 0) + counts.get("XPASS", 0)  # SKIP and XFAIL do not fail the run
    print(f"SUMMARY: {counts} in {time.time() - t0:.0f}s -> {'PASS' if not bad and results else 'FAIL'}", flush=True)
    sys.exit(1 if bad or not results else 0)


if __name__ == "__main__":
    main()
