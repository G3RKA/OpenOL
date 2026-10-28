"""Refresh output_sha256 in sites.json after a code change: python -I refresh_hash.py <original OLGame.exe>   (run build.py first, then build.py again)."""
import copy, hashlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apply_patch

cfg = json.load(open(os.path.join(HERE, "olfix.json")))
c = copy.deepcopy(cfg)
c["output_sha256"] = None
out = apply_patch.apply(open(sys.argv[1], "rb").read(), c)
h = hashlib.sha256(out).hexdigest()
path = os.path.join(HERE, "sites.json")
text = open(path, encoding="utf-8").read()
text = text.replace(cfg["output_sha256"], h)
open(path, "w", encoding="utf-8", newline="").write(text)
print("output_sha256 =", h)
