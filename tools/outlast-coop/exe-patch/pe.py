"""Minimal PE64 helpers for the OLGame.exe patch: RVA <-> file offset, byte patches, and appending one executable section.
Pure Python, no dependencies. Works on bytes in memory; nothing here touches a file you did not pass in.
"""
import struct

IMAGE_SCN_CNT_CODE = 0x20
IMAGE_SCN_MEM_EXECUTE = 0x20000000
IMAGE_SCN_MEM_READ = 0x40000000
IMAGE_SCN_MEM_WRITE = 0x80000000


def _align(v, a):
    return (v + a - 1) // a * a


class PE:
    def __init__(self, data):
        self.d = bytearray(data)
        self.pe = struct.unpack_from("<I", self.d, 0x3C)[0]
        assert self.d[self.pe:self.pe + 4] == b"PE\0\0"
        self.nsec = struct.unpack_from("<H", self.d, self.pe + 6)[0]
        self.opt = self.pe + 24
        assert struct.unpack_from("<H", self.d, self.opt)[0] == 0x20B, "PE32+ expected"
        optsz = struct.unpack_from("<H", self.d, self.pe + 20)[0]
        self.imagebase = struct.unpack_from("<Q", self.d, self.opt + 24)[0]
        self.secal, self.fileal = struct.unpack_from("<II", self.d, self.opt + 32)
        self.soh = struct.unpack_from("<I", self.d, self.opt + 60)[0]
        self.st = self.opt + optsz

    def sections(self):
        out = []
        for i in range(self.nsec):
            o = self.st + i * 40
            name, vs, va, rs, rp = struct.unpack_from("<8sIIII", self.d, o)
            ch = struct.unpack_from("<I", self.d, o + 36)[0]
            out.append(dict(name=name.rstrip(b"\0").decode(), vs=vs, va=va, rs=rs, rp=rp, ch=ch, hdr=o))
        return out

    def rva_to_off(self, rva):
        for s in self.sections():
            if s["va"] <= rva < s["va"] + max(s["vs"], s["rs"]):
                if rva - s["va"] >= s["rs"]:
                    raise ValueError(f"RVA {rva:#x} is in the zero-filled part of {s['name']}")
                return s["rp"] + rva - s["va"]
        raise ValueError(f"RVA {rva:#x} is in no section")

    def read(self, rva, n):
        o = self.rva_to_off(rva)
        return bytes(self.d[o:o + n])

    def write(self, rva, data, expect=None):
        """Overwrite bytes at an RVA; if expect is given the current bytes must match (guards against a wrong file or address)."""
        o = self.rva_to_off(rva)
        if expect is not None and bytes(self.d[o:o + len(expect)]) != expect:
            raise ValueError(f"bytes at {rva:#x} are {bytes(self.d[o:o + len(expect)]).hex()}, expected {expect.hex()}")
        self.d[o:o + len(data)] = data

    def add_section(self, name, payload, characteristics=IMAGE_SCN_CNT_CODE | IMAGE_SCN_MEM_EXECUTE | IMAGE_SCN_MEM_READ):
        """Append a section after the last one; returns its RVA. The section header must fit in the header slack."""
        secs = self.sections()
        last = max(secs, key=lambda s: s["va"])
        hdr_end = self.st + self.nsec * 40
        if hdr_end + 40 > secs[0]["rp"]:
            raise ValueError("no room for another section header")
        if bytes(self.d[hdr_end:hdr_end + 40]) != b"\0" * 40:
            raise ValueError("section header slack is not empty")
        va = _align(last["va"] + max(last["vs"], last["rs"]), self.secal)
        rp = _align(len(self.d), self.fileal)
        rs = _align(len(payload), self.fileal)
        self.d.extend(b"\0" * (rp - len(self.d)))
        self.d.extend(payload + b"\0" * (rs - len(payload)))
        struct.pack_into("<8sIIIIIIHHI", self.d, hdr_end, name.encode().ljust(8, b"\0"), len(payload), va, rs, rp, 0, 0, 0, 0, characteristics)
        struct.pack_into("<H", self.d, self.pe + 6, self.nsec + 1)
        self.nsec += 1
        struct.pack_into("<I", self.d, self.opt + 56, _align(va + len(payload), self.secal))     # SizeOfImage
        # the checksum is not used by the loader for an exe; zero it so it is not stale
        struct.pack_into("<I", self.d, self.opt + 64, 0)
        return va

    def bytes(self):
        return bytes(self.d)


def rel32(from_rva_next, to_rva):
    """Displacement for a 5-byte call/jmp whose next instruction is at from_rva_next."""
    return struct.pack("<i", to_rva - from_rva_next)
