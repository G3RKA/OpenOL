"""Patch OLGame.exe of OpenOL 2.1.0 (one real copy of every map enemy, more features to come).

  python -I apply_patch.py <input OLGame.exe> <output OLGame.exe>

Reads the input (never writes to it), refuses any file whose SHA-256 is not the OpenOL 2.1.0 exe the patch was written for, appends one section with
the code of olfix.c and rewrites the sites listed in olfix.json (taken from sites.json), each only if the bytes there are the expected ones.
Re-running on the output is refused (the SHA-256 differs).
"""
import hashlib, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe

RWX_CODE_DATA = 0xE0000060     # code + initialized data + execute + read + write (a section that carries mutable state)


def apply(data, cfg):
    """Returns the patched bytes of `data` (checks every expectation; raises ValueError on any mismatch)."""
    if hashlib.sha256(data).hexdigest() != cfg["input_sha256"]:
        raise ValueError(f"the input is not the exe this patch is for (SHA-256 {cfg['input_sha256']})")
    p = pe.PE(data)
    code = bytes.fromhex(cfg["hex"])
    sec = cfg["section"]
    if sec.get("data_size", 0):
        page = pe._align(len(code), 0x1000)
        payload, chars = code + b"\0" * (page - len(code)) + b"\0" * sec["data_size"], RWX_CODE_DATA
    else:
        payload, chars = code, pe.IMAGE_SCN_CNT_CODE | pe.IMAGE_SCN_MEM_EXECUTE | pe.IMAGE_SCN_MEM_READ
    cave = p.add_section(sec["name"], payload, chars)
    if cave != int(sec["cave_rva"], 16):
        raise ValueError(f"the new section landed at {cave:#x}, the code was built for {sec['cave_rva']}")
    for s in cfg["sites"]:
        rva, expect, target = int(s["rva"], 16), bytes.fromhex(s["expect"]), cave + cfg["entries"][s["symbol"]]
        if s["kind"] == "call32":
            assert len(expect) == 5 and expect[0] == 0xE8
            new = b"\xE8" + pe.rel32(rva + 5, target)
        elif s["kind"] == "call_vt6":
            assert len(expect) == 6 and expect[0] == 0xFF
            new = b"\xE8" + pe.rel32(rva + 5, target) + b"\x90"
        elif s["kind"] == "vtable_slot":     # an absolute pointer; its base relocation entry already exists in the exe
            assert len(expect) == 8
            new = struct.pack("<Q", p.imagebase + target)
        else:
            raise ValueError(f"unknown site kind {s['kind']}")
        p.write(rva, new, expect=expect)
    out = p.bytes()
    want = cfg.get("output_sha256")
    if want and hashlib.sha256(out).hexdigest() != want:
        raise ValueError("the patched exe differs from the reference build (output_sha256 of sites.json)")
    return out


def main():
    src, dst = sys.argv[1], sys.argv[2]
    if os.path.abspath(src) == os.path.abspath(dst):
        sys.exit("the output must be a different file")
    cfg = json.load(open(os.path.join(HERE, "olfix.json")))
    try:
        out = apply(open(src, "rb").read(), cfg)
    except ValueError as e:
        sys.exit(f"refusing: {e}")
    open(dst, "wb").write(out)
    print(f"patched copy written: {dst}\n  section {cfg['section']['name']} at RVA {cfg['section']['cave_rva']}, {len(cfg['hex']) // 2} bytes of code, "
          f"{len(cfg['sites'])} sites\n  sha256 {hashlib.sha256(out).hexdigest()}")


if __name__ == "__main__":
    main()
