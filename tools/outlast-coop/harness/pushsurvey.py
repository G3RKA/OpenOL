"""Find checkpoints whose level has pushable objects: one client, load each checkpoint, count PUSH packets the client sends.
python -I pushsurvey.py <checkpoint> [<checkpoint> ...]   (needs `ol.py up` + `ol.py launch 1 prison_persistent` first)"""
import os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ol
c = ol.clients()[0]
port = str(c["port"])
for name in sys.argv[1:]:
    off = os.path.getsize(ol.tap_log())
    ok = ol.cp(0, name)
    time.sleep(6)
    with open(ol.tap_log(), "rb") as f:
        f.seek(off)
        txt = f.read().decode("utf-8", "replace")
    n_init = len(re.findall(rf"C>R {port} PUSH 0x03", txt))
    n_state = len(re.findall(rf"C>R {port} PUSH 0x01", txt))
    print(f"{name}: applied={ok} PUSH_INIT={n_init} PUSH_STATE={n_state}", flush=True)
