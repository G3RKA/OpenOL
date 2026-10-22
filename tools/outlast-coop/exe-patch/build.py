"""Compile olfix.c into position independent code and write olfix.json (code, entry offsets, the site table of sites.json).
  python -I build.py            needs MinGW gcc, objdump, objcopy and nm on PATH
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
src, obj, binf = (os.path.join(HERE, n) for n in ("olfix.c", "olfix.o", "olfix.bin"))
cfg = json.load(open(os.path.join(HERE, "sites.json")))
cave = int(cfg["section"]["cave_rva"], 16)
subprocess.run(["gcc", "-O2", "-ffreestanding", "-fno-asynchronous-unwind-tables", "-fno-stack-protector", "-fno-ident", "-mno-avx", "-mno-red-zone",
                f"-DCAVE_RVA={cave:#x}", f"-DDATA_SIZE={int(cfg['section'].get('data_size', 0))}", "-c", src, "-o", obj], check=True)
rel = subprocess.run(["objdump", "-r", obj], capture_output=True, text=True).stdout
if "REL32" in rel or "ADDR64" in rel:
    sys.exit("the object has relocations; the blob would not be position independent:\n" + rel)
subprocess.run(["objcopy", "-O", "binary", "-j", ".text", obj, binf], check=True)
syms = {}
for line in subprocess.run(["nm", obj], capture_output=True, text=True).stdout.splitlines():
    addr, kind, name = line.split()
    if kind == "T":
        syms[name] = int(addr, 16)
for s in cfg["sites"]:
    if s["symbol"] not in syms:
        sys.exit(f"site {s['name']}: symbol {s['symbol']} is not in the object")
blob = open(binf, "rb").read()
json.dump({"entries": syms, "size": len(blob), "hex": blob.hex(), **cfg}, open(os.path.join(HERE, "olfix.json"), "w"), indent=1)
os.remove(obj); os.remove(binf)
print("built", len(blob), "bytes, entries", syms)
