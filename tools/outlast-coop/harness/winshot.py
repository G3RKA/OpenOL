"""Capture ONLY one game window (never the desktop): python -I winshot.py <out.png>   (client index 0, after ol.launch)."""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol

def shot(idx, out):
    hwnd, r = ol.window_rect(ol.clients()[idx]["pid"])
    w, h = r[2], r[3]
    ps = ("Add-Type -AssemblyName System.Drawing;"
          f"$b=New-Object System.Drawing.Bitmap {w},{h};$g=[System.Drawing.Graphics]::FromImage($b);"
          f"$g.CopyFromScreen({r[0]},{r[1]},0,0,$b.Size);$b.Save('{out}')")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)

if __name__ == "__main__":
    shot(0, sys.argv[1])
