"""Helpers for the OpenOL 2.2.0 test copy (test22). The traffic is encrypted, so the udp_tap proxy of the 2.1.0 harness cannot be used: the relay is started
directly (port 17777, loopback) and the clients connect to it; everything is judged from the game and relay logs and the process state.

  python -I v22.py up <n> [<map>]     relay + n clients on a map (default prison_persistent), prints pids and log paths
  python -I v22.py down               stop what 'up' started (only by the pids it recorded)
  python -I v22.py log <idx> [<pattern>]   lines of a client log matching a regex (default: multiplayer lines)
"""
import json, os, re, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import olwin

GAME = os.environ.get("OL_GAME_DIR22", r"<test copy 2.2.0>\Binaries\Win64")
LOGS = os.environ.get("OL_LOG_DIR22", r"<test copy 2.2.0>\OLGame\Logs")
RELAY = os.environ.get("OL_RELAY22", os.path.join(HERE, "relay22", "OpenOL_Relay.exe"))
REG = os.path.join(HERE, "v22_reg.json")
PORT = 7777


def save(reg):
    json.dump(reg, open(REG, "w"))


def load():
    try:
        return json.load(open(REG))
    except OSError:
        return {"relay": None, "clients": []}


def start_relay():
    out = open(os.path.join(HERE, "relay22", "relay_run.log"), "w")
    p = subprocess.Popen([RELAY, "--port", str(PORT), "--ip", "127.0.0.1", "--name", "CoopTest22"], cwd=os.path.join(HERE, "relay22"),
                         stdin=subprocess.PIPE, stdout=out, stderr=subprocess.STDOUT, creationflags=0x00000200)
    time.sleep(2)
    return p.pid


def read_log(path):
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def launch_client(i, mapname):
    log = f"mp22_{chr(97 + i)}.log"
    pid = int(subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Start-Process -FilePath '{GAME}\\OLGame.exe' -WorkingDirectory '{GAME}' -PassThru "
         f"-ArgumentList '{mapname}?game=Multiplayer.MultiplayerGame','-nostartupmovies','-nosteam','-FORCELOGFLUSH','-log={log}').Id"],
        capture_output=True, text=True).stdout.strip())
    logp = os.path.join(LOGS, log)
    for _ in range(90):
        if "Wwise(R) SDK Version" in read_log(logp):
            break
        time.sleep(1)
    for _ in range(12):
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "olwin.py"), "wake", str(pid)], capture_output=True)
        time.sleep(4)
        if re.search(r"Connected|Critical", read_log(logp)):
            break
    return {"idx": i, "pid": pid, "log": logp}


def up(n, mapname):
    reg = {"relay": start_relay(), "clients": []}
    save(reg)
    for i in range(n):
        reg["clients"].append(launch_client(i, mapname))
        save(reg)
    return reg


def down():
    reg = load()
    for pid in [c["pid"] for c in reg["clients"]] + ([reg["relay"]] if reg["relay"] else []):
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    save({"relay": None, "clients": []})


def alive(pid):
    return str(pid) in subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "up":
        r = up(int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "prison_persistent")
        print(json.dumps(r))
    elif cmd == "down":
        down()
    elif cmd == "log":
        c = load()["clients"][int(sys.argv[2])]
        pat = re.compile(sys.argv[3] if len(sys.argv) > 3 else r"\[MP\]|MpConn|Connected|Critical|Assertion|Mp")
        for l in read_log(c["log"]).splitlines():
            if pat.search(l):
                print(l[:200])
