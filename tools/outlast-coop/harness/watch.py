"""Timeline of a co-op test: one line per second from the tap's state.json, screenshots every N s.

  python -I watch.py <seconds> <shot_dir> [shot_every=3] [state=state.json] [A=port] [B=port]

Per line: hero hp / special move / position per client, each enemy's position and mode as sent by its
owner, distance enemy->each hero, and STALE if a hero or enemy has not updated for >3 s.
"""
import json
import math
import os
import subprocess
import sys
import time

PS = r"""Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height
$g=[System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size)
(New-Object System.Drawing.Bitmap $bmp,960,540).Save('{out}')"""


def load(statef):
    for _ in range(10):
        try:
            with open(statef, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            time.sleep(0.05)
    return None


def main():
    secs, shot_dir = float(sys.argv[1]), sys.argv[2]
    every = float(sys.argv[3]) if len(sys.argv) > 3 else 3
    statef = sys.argv[4] if len(sys.argv) > 4 else "state.json"
    os.makedirs(shot_dir, exist_ok=True)
    end, next_shot = time.time() + secs, 0
    while time.time() < end:
        now = time.time()
        s = load(statef)
        if s is None:
            print("state unreadable", flush=True)
        else:
            parts = []
            heroes = s["heroes"]
            for port, h in sorted(heroes.items()):
                stale = " STALE" if now - h["t"] > 3 else ""
                parts.append(f"{port}: hp={h.get('hp')} sm={h.get('smove')} ({h['x']:.0f},{h['y']:.0f}){stale}")
            for name, e in s["enemies"].items():
                for key, pos in e.items():
                    if not key.startswith("C>R") or key.endswith((" mode", " t", " look")):
                        continue
                    age = now - e.get(key + " t", 0)
                    d = ", ".join(f"d{p}={math.dist(pos[:2], (h['x'], h['y'])):.0f}" for p, h in sorted(heroes.items()))
                    parts.append(f"{name}@{key.split()[1]}: ({pos[0]},{pos[1]},{pos[2]}) mode={e.get(key + ' mode')} look={e.get(key + ' look')} {d}"
                                 + (" STALE" if age > 3 else ""))
            print(time.strftime("%H:%M:%S"), " | ".join(parts), flush=True)
        if now >= next_shot:
            next_shot = now + every
            out = os.path.join(shot_dir, time.strftime("%H%M%S") + ".png")
            subprocess.Popen(["powershell", "-NoProfile", "-Command", PS.replace("{out}", out)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)


if __name__ == "__main__":
    main()
