"""Capture only the window of a 2.2.0 client (never the desktop): python -I v22_shot.py <client idx> <out.png>. Keep the pictures local."""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol, v22


def shot(idx, out):
    hwnd, r = ol.window_rect(v22.load()["clients"][idx]["pid"])
    ps = ("Add-Type -AssemblyName System.Drawing;"
          f"$b=New-Object System.Drawing.Bitmap {r[2]},{r[3]};$g=[System.Drawing.Graphics]::FromImage($b);"
          f"$g.CopyFromScreen({r[0]},{r[1]},0,0,$b.Size);$b.Save('{out}')")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


if __name__ == "__main__":
    shot(int(sys.argv[1]), sys.argv[2])
