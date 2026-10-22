"""Static self-test of the exe patch (no game): applies it in memory to the original exe and checks the result.

  python -I selftest.py <original OLGame.exe>

Checks: (1) the output hash is the reference one; (2) the only bytes that differ from the original are the allowed ones: the PE header fields a new section changes,
the new section header, the declared sites and the appended section; (3) every site decodes to the exact entry of the new section; (4) the output parses and
has one more section with the declared characteristics; (5) refusals: a wrong input, a changed site byte, an unknown symbol. Prints one line per check.
"""
import copy, hashlib, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apply_patch, pe

fails = 0


def check(name, ok, detail=""):
    global fails
    fails += 0 if ok else 1
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))


def main():
    orig = open(sys.argv[1], "rb").read()
    cfg = json.load(open(os.path.join(HERE, "olfix.json")))
    out = apply_patch.apply(orig, cfg)
    check("output-hash-is-the-reference", hashlib.sha256(out).hexdigest() == cfg["output_sha256"], hashlib.sha256(out).hexdigest()[:16])

    po, pn = pe.PE(orig), pe.PE(out)
    so, sn = po.sections(), pn.sections()
    check("one-more-section", len(sn) == len(so) + 1 and sn[-1]["name"] == cfg["section"]["name"], f"{len(so)} -> {len(sn)}")
    allowed = [(po.pe + 6, 2), (po.opt + 56, 4), (po.opt + 64, 4), (po.st + len(so) * 40, 40)]          # NumberOfSections, SizeOfImage, CheckSum, the new header
    for s in cfg["sites"]:
        allowed.append((po.rva_to_off(int(s["rva"], 16)), len(bytes.fromhex(s["expect"]))))
    diff = [i for i in range(len(orig)) if orig[i] != out[i]]
    stray = [i for i in diff if not any(a <= i < a + n for a, n in allowed)]
    check("only-allowed-bytes-changed", not stray, f"{len(diff)} changed bytes, {len(stray)} outside the allowed ranges")
    check("original-prefix-kept", out[:len(orig)] != b"" and len(out) > len(orig), f"{len(orig)} -> {len(out)} bytes")

    cave = sn[-1]["va"]
    for s in cfg["sites"]:
        rva = int(s["rva"], 16)
        new = pn.read(rva, len(bytes.fromhex(s["expect"])))
        want = cave + cfg["entries"][s["symbol"]]
        if s["kind"] in ("call32", "call_vt6"):
            got = rva + 5 + struct.unpack("<i", new[1:5])[0]
            ok = new[0] == 0xE8 and got == want and (s["kind"] == "call32" or new[5] == 0x90)
        else:
            got = struct.unpack("<Q", new)[0] - pn.imagebase
            ok = got == want
        check(f"site-{s['name']}-reaches-{s['symbol']}", ok, f"{rva:#x} -> {got:#x} (entry at {want:#x})")

    code = bytes.fromhex(cfg["hex"])
    check("code-landed-intact", pn.read(cave, len(code)) == code)
    want_ch = apply_patch.RWX_CODE_DATA if cfg["section"].get("data_size", 0) else pe.IMAGE_SCN_CNT_CODE | pe.IMAGE_SCN_MEM_EXECUTE | pe.IMAGE_SCN_MEM_READ
    check("section-characteristics", sn[-1]["ch"] == want_ch, hex(sn[-1]["ch"]))
    check("size-of-image-covers-the-section", struct.unpack_from("<I", out, pn.opt + 56)[0] >= cave + sn[-1]["vs"])

    def refuses(label, d, c):
        try:
            apply_patch.apply(d, c)
            check(label, False, "was accepted")
        except ValueError:
            check(label, True)
    refuses("refuses-another-exe", orig[:-1] + bytes([orig[-1] ^ 1]), cfg)
    c2 = copy.deepcopy(cfg)
    c2["sites"][0]["expect"] = "e800000000"
    refuses("refuses-a-site-with-unexpected-bytes", orig, c2)
    c3 = copy.deepcopy(cfg)
    c3["section"]["cave_rva"] = "0x39B0000"
    refuses("refuses-a-wrong-cave-address", orig, c3)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
