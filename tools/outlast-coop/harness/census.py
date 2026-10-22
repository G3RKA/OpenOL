"""Enemy census of a running game client, read straight from its memory (read-only: OpenProcess with VM_READ, nothing is written).

  python -I census.py <pid> [<pid> ...]

Uses the structure of OpenOL 2.1.0's AMultiplayerController (offsets from the decompiled OLGame.exe, see patches/native-one-owner):
  GMultiplayerController   image base + 0x36b6908
  CachedEnemies            ctrl + 0xe78 (data), + 0xe80 (count)          the client's OWN enemies (real AI copies)
  RemoteEnemies            ctrl + 0xeb8 (data), + 0xec0 (count), 0x44 each: DummyEnemy +0x10, OwnerID +0x18   puppets of other clients' enemies
  AActor: Location +0x80 (3 floats), Class +0x50; AOLEnemyPawn: Health +0x37c, flag bytes +0xe8 (8 = bDeleteMe) and +0xec (0x800000 = bPendingDelete)
Only valid for the offsets of that exact exe (both the original and the one-owner patched exe have them: the patch adds code, it moves nothing).
"""
import ctypes
import ctypes.wintypes as w
import json
import struct
import sys

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
ps = ctypes.WinDLL("psapi", use_last_error=True)
k32.OpenProcess.restype = w.HANDLE
k32.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
k32.ReadProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
ps.EnumProcessModules.argtypes = [w.HANDLE, ctypes.POINTER(ctypes.c_void_p), w.DWORD, ctypes.POINTER(w.DWORD)]

RVA_CTRL = 0x36B6908


class Proc:
    def __init__(self, pid, write=False):
        # VM_READ | QUERY_INFORMATION; write=True adds VM_WRITE | VM_OPERATION (only for the data area of our own patch, see olmail.py)
        self.h = k32.OpenProcess(0x0010 | 0x0400 | (0x0020 | 0x0008 if write else 0), False, pid)
        if not self.h:
            raise OSError(f"cannot open pid {pid}")
        mods = (ctypes.c_void_p * 1)()
        need = w.DWORD()
        if not ps.EnumProcessModules(self.h, mods, ctypes.sizeof(mods), ctypes.byref(need)):
            raise OSError("EnumProcessModules failed")
        self.base = mods[0]

    def rd(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)) or got.value != n:
            return None
        return buf.raw

    def wr(self, addr, data):
        n = ctypes.c_size_t()
        return bool(k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(n))) and n.value == len(data)

    def u64(self, a):
        b = self.rd(a, 8)
        return struct.unpack("<Q", b)[0] if b else None

    def i32(self, a):
        b = self.rd(a, 4)
        return struct.unpack("<i", b)[0] if b else None

    def actor(self, a):
        loc = self.rd(a + 0x80, 12)
        cls = self.u64(a + 0x50)
        hp = self.i32(a + 0x37C)
        fa = self.rd(a + 0xE8, 1)
        fb = self.rd(a + 0xEC, 4)
        if not loc or cls is None or hp is None or not fa or not fb:
            return None
        x, y, z = struct.unpack("<3f", loc)
        gone = bool(fa[0] & 8) or bool(struct.unpack("<I", fb)[0] & 0x800000)
        return {"addr": hex(a), "class": hex(cls), "x": round(x), "y": round(y), "z": round(z), "hp": hp, "gone": gone}


def census(pid):
    p = Proc(pid)
    ctrl = p.u64(p.base + RVA_CTRL)
    if not ctrl:
        return {"pid": pid, "error": "no multiplayer controller (not connected yet?)"}
    out = {"pid": pid, "own": [], "puppets": []}
    data, n = p.u64(ctrl + 0xE78), p.i32(ctrl + 0xE80)
    for i in range(max(0, min(n or 0, 256))):
        a = p.u64(data + 8 * i)
        d = p.actor(a) if a else None
        if d:
            out["own"].append(d)
    data, n = p.u64(ctrl + 0xEB8), p.i32(ctrl + 0xEC0)
    for i in range(max(0, min(n or 0, 256))):
        rec = p.rd(data + 0x44 * i, 0x44)
        if not rec:
            continue
        dummy, owner = struct.unpack_from("<Q", rec, 0x10)[0], struct.unpack_from("<i", rec, 0x18)[0]
        d = p.actor(dummy) if dummy else None
        out["puppets"].append({"owner": owner, "actor": d})
    return out


def alive_own(c):
    return [e for e in c.get("own", []) if not e["gone"] and e["hp"] > 0]


def alive_puppets(c):
    return [r for r in c.get("puppets", []) if r["actor"] and not r["actor"]["gone"]]


if __name__ == "__main__":
    for pid in map(int, sys.argv[1:]):
        print(json.dumps(census(pid)))
