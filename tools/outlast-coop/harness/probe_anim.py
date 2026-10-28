"""Enemy animations, owner against puppet, read-only from memory (no mouse, no keyboard). Needs the exe patch v7 (data area with the anim counters).

  python -I probe_anim.py <checkpoint> [<checkpoint> ...] [--wait 8] [--seconds 25] [--disable 8|16]   (8 = the twin: animations off; 16 = no anim-set handover from the dropped copy, the puppet must look the sets up by path)

Per checkpoint: both clients load it through the mailbox (one after the other, shared checkpoint off, like the sweep), then for every second:
  owner side  each own enemy: Bot->bAnimating (bot+0x4bc bit 14), pawn->bIsAnimatingFullBody (pawn+0x2bf8 bit 0x10), Bot->CurrentAnimation FName (bot+0x618: index, number)
  puppet side each puppet: bIsAnimatingFullBody and whether it has a FullBodyAnimSlot (pawn+0x794)
and at the end the patch counters (cnt_anim_sent / recv / played / dropped) of both clients. A checkpoint with a waypoint-animation enemy shows owner
rows with anim=1 and, with the patch, puppet rows with fullbody=1 at the same time; on the v6 exe (or with disable bit 3 set) the puppet stays at 0.
The offsets are the ones of native-fix-research.md, Addendum 4; a read that fails prints None instead of guessing.
"""
import os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol, census, olmail
from sweep import load

PAWN_BOT, PAWN_FLAGS, PAWN_SLOT, PAWN_SPAWNER_SETS = 0x2BD8, 0x2BF8, 0x794, 0x2D7C      # SpawnerAnimSets: the sets the level's actor factory gave this enemy
BOT_FLAGS, BOT_CURANIM = 0x4BC, 0x618


def own_rows(p, ctrl):
    rows = []
    data, n = p.u64(ctrl + 0xE78), p.i32(ctrl + 0xE80)
    for i in range(max(0, min(n or 0, 64))):
        a = p.u64(data + 8 * i)
        d = p.actor(a) if a else None
        if not d or d["gone"] or d["hp"] <= 0:
            continue
        bot = p.u64(a + PAWN_BOT)
        bf = p.rd(bot + BOT_FLAGS, 4) if bot else None
        nm = p.rd(bot + BOT_CURANIM, 8) if bot else None
        pf = p.rd(a + PAWN_FLAGS, 4)
        rows.append({"class": d["class"][-4:], "anim": (struct.unpack("<I", bf)[0] >> 14) & 1 if bf else None,
                     "fullbody": (struct.unpack("<I", pf)[0] >> 4) & 1 if pf else None,
                     "name": struct.unpack("<ii", nm) if nm else None, "sets": p.i32(a + PAWN_SPAWNER_SETS + 8)})
    return rows


def puppet_rows(p, ctrl):
    rows = []
    data, n = p.u64(ctrl + 0xEB8), p.i32(ctrl + 0xEC0)
    for i in range(max(0, min(n or 0, 64))):
        rec = p.rd(data + 0x44 * i, 0x44)
        if not rec:
            continue
        dummy = struct.unpack_from("<Q", rec, 0x10)[0]
        d = p.actor(dummy) if dummy else None
        if not d or d["gone"]:
            continue
        pf = p.rd(dummy + PAWN_FLAGS, 4)
        rows.append({"owner": struct.unpack_from("<i", rec, 0x18)[0], "class": d["class"][-4:],
                     "net_anim": struct.unpack_from("<I", rec, 0x40)[0],
                     "fullbody": (struct.unpack("<I", pf)[0] >> 4) & 1 if pf else None,
                     "slot": bool(p.u64(dummy + PAWN_SLOT)), "sets": p.i32(dummy + PAWN_SPAWNER_SETS + 8)})
    return rows


def main():
    args = sys.argv[1:]
    wait, seconds, extra = 8.0, 25, 0
    cps = []
    i = 0
    while i < len(args):
        if args[i] == "--wait":
            wait = float(args[i + 1]); i += 2
        elif args[i] == "--seconds":
            seconds = int(args[i + 1]); i += 2
        elif args[i] == "--disable":                 # extra kill-switch bits on both clients (8 = enemy animations): the twin run
            extra = int(args[i + 1], 0); i += 2
        else:
            cps.append(args[i]); i += 1
    if not cps:
        sys.exit(__doc__)
    ol.up()
    ol.launch(2, "prison_persistent")
    cs = ol.clients()
    for c in cs:
        olmail.set_disable(c["pid"], 4 | extra)  # no shared checkpoint: load both ourselves (plus the bits of --disable)
    procs = [census.Proc(c["pid"]) for c in cs]
    for cp in cps:
        for c in cs:
            print(f"load {cp} on client {c['idx']}: {load(c, cp)}", flush=True)
        time.sleep(wait)
        both = 0
        for sec in range(seconds):
            line = []
            owner_anim = puppet_full = 0
            for c, p in zip(cs, procs):
                ctrl = p.u64(p.base + census.RVA_CTRL)
                if not ctrl:
                    line.append(f"client {c['idx']}: no controller")
                    continue
                own, pup = own_rows(p, ctrl), puppet_rows(p, ctrl)
                owner_anim += sum(1 for r in own if r["anim"] and r["fullbody"])
                puppet_full += sum(1 for r in pup if r["fullbody"])
                line.append(f"client {c['idx']}: own {own} puppets {pup}")
            both += 1 if owner_anim and puppet_full else 0
            print(f"t+{sec:2d}s  " + " | ".join(line), flush=True)
            time.sleep(1)
        print(f"{cp}: seconds with an animating owner and an animating puppet: {both}", flush=True)
    for c in cs:
        m = olmail.read(c["pid"])
        print("client", c["idx"], {k: m.get(k) for k in ("cnt_anim_sent", "cnt_anim_recv", "cnt_anim_played", "cnt_anim_dropped", "cnt_anim_resolved", "cnt_own_destroyed", "cnt_puppet_destroyed")}, flush=True)
    ol.down()


if __name__ == "__main__":
    main()
