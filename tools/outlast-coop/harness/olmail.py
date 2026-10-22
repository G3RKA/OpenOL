"""Host side of the patch's data area (see exe-patch/sites.json "layout"): read the counters and set the kill switch of a running client.

  python -I olmail.py <pid> [<pid> ...]                 print the data area of each client
  python -I olmail.py <pid> disable one_owner|none      set or clear the one-owner kill switch (a twin without swapping exes)

The area is part of the patched exe's own section (writable); only these few u32 fields are ever written, from outside, by this tool.
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import census

CFG = None
for cand in (os.path.join(HERE, "..", "nativepatch", "olfix.json"), os.path.join(HERE, "..", "exe-patch", "olfix.json")):
    if os.path.exists(cand):
        CFG = json.load(open(cand))
        break
if CFG is None:
    sys.exit("olfix.json not found next to the harness")
CAVE, OFF, LAY = int(CFG["section"]["cave_rva"], 16), int(CFG["section"]["data_offset"], 16), CFG["layout"]
MAGIC = 0x5846504F


def read(pid):
    p = census.Proc(pid)
    raw = p.rd(p.base + CAVE + OFF, 0x40)
    if raw is None:
        return {"pid": pid, "error": "data area not readable (not the patched exe?)"}
    f = {k: struct.unpack_from("<I", raw, v)[0] for k, v in LAY.items()}
    f["pid"] = pid
    f["hooks_ran"] = f["magic"] == MAGIC
    return f


def set_disable(pid, mask):
    p = census.Proc(pid, write=True)
    return p.wr(p.base + CAVE + OFF + LAY["disable"], struct.pack("<I", mask))


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 3 and a[1] == "disable":
        ok = set_disable(int(a[0]), {"one_owner": 1, "none": 0}[a[2]])
        print("written" if ok else "write failed")
    else:
        for pid in map(int, a):
            print(json.dumps(read(pid)))
