"""One owner for every map enemy: patch OLGame.exe of OpenOL 2.1.0.

  python -I apply_patch.py <input OLGame.exe> <output OLGame.exe>

Reads the input (never writes to it), refuses any file whose SHA-256 is not the OpenOL 2.1.0 exe it was written for, appends one section with
the code of olfix.c and redirects two call sites to it. Re-running on the output is refused (the SHA-256 differs).
"""
import hashlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe

EXPECT_SHA256 = "2e58afbb1203d04476581f34216428d1dfc96228e5f3df8c6881323c56c93346"   # OLGame.exe of OpenOL 2.1.0 on Outlast Steam build 576074
SITE_APPLYSPAWN = 0x172B0B4        # E8 rel32: call ApplySpawn(UEnemyChannel*, sender, ...) in OnBinaryPacket
SITE_SENDSPAWN = 0x1736CAB         # FF 90 68 02 00 00: call [rax+0x268] = vtable SendSpawn, inside UEnemyChannel::TickSend


def main():
    src, dst = sys.argv[1], sys.argv[2]
    if os.path.abspath(src) == os.path.abspath(dst):
        sys.exit("the output must be a different file")
    data = open(src, "rb").read()
    h = hashlib.sha256(data).hexdigest()
    if h != EXPECT_SHA256:
        sys.exit(f"refusing: SHA-256 of the input is {h}, this patch is for {EXPECT_SHA256} (OpenOL 2.1.0 on Steam build 576074)")
    blob = json.load(open(os.path.join(HERE, "olfix.json")))
    code = bytes.fromhex(blob["hex"])
    p = pe.PE(data)
    cave = p.add_section(".olfix", code)
    ent = blob["entries"]
    old = p.read(SITE_APPLYSPAWN, 5)
    if old[0] != 0xE8:
        sys.exit("unexpected bytes at the ApplySpawn call site")
    p.write(SITE_APPLYSPAWN, b"\xE8" + pe.rel32(SITE_APPLYSPAWN + 5, cave + ent["my_ApplySpawn"]), expect=old)
    p.write(SITE_SENDSPAWN, b"\xE8" + pe.rel32(SITE_SENDSPAWN + 5, cave + ent["my_SendSpawn"]) + b"\x90", expect=bytes.fromhex("ff9068020000"))
    open(dst, "wb").write(p.bytes())
    print(f"patched copy written: {dst}\n  new section .olfix at RVA {cave:#x}, {len(code)} bytes\n  sha256 {hashlib.sha256(p.bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
