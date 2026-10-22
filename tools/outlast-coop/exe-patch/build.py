"""Compile olfix.c into olfix.bin (position independent, no relocations) and write the entry offsets next to it.
  python -I build.py            needs MinGW gcc, objdump, objcopy and nm on PATH
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
src, obj, binf = (os.path.join(HERE, n) for n in ("olfix.c", "olfix.o", "olfix.bin"))
subprocess.run(["gcc", "-O2", "-ffreestanding", "-fno-asynchronous-unwind-tables", "-fno-stack-protector", "-fno-ident", "-mno-avx", "-mno-red-zone",
                "-c", src, "-o", obj], check=True)
rel = subprocess.run(["objdump", "-r", obj], capture_output=True, text=True).stdout
if "REL32" in rel or "ADDR64" in rel:
    sys.exit("the object has relocations; the blob would not be position independent:\n" + rel)
subprocess.run(["objcopy", "-O", "binary", "-j", ".text", obj, binf], check=True)
syms = {}
for line in subprocess.run(["nm", obj], capture_output=True, text=True).stdout.splitlines():
    addr, kind, name = line.split()
    if kind == "T":
        syms[name] = int(addr, 16)
blob = open(binf, "rb").read()
json.dump({"entries": syms, "size": len(blob), "hex": blob.hex()}, open(os.path.join(HERE, "olfix.json"), "w"), indent=1)
print("built", len(blob), "bytes, entries", syms)
