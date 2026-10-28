"""Build and run the host test of the exe patch's C code (no game): python -I hosttest.py     (needs MinGW gcc)"""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
exe = os.path.join(HERE, "hosttest.exe")
subprocess.run([sys.executable, "-I", os.path.join(HERE, "build.py"), "--keep"], check=True, cwd=HERE, stdout=subprocess.DEVNULL)
try:
    subprocess.run(["gcc", "-O0", "-g", "-Wall", "-Wno-unused-function", "-I", HERE, os.path.join(HERE, "hosttest.c"), "-o", exe], check=True)
    r = subprocess.run([exe])
finally:
    for f in ("olfix.o", "olfix_layout.h", "hosttest.exe"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            os.remove(p)
sys.exit(r.returncode)
