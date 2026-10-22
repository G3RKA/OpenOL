"""Dry run of the 'host + friend' guide on one PC: the relay started exactly as the guide says (default bind, UDP 7777), one client that
connects to this PC's LAN address (not 127.0.0.1) with the ini keys from the guide. Needs the owner to answer a Windows Firewall prompt if one appears.
  python -I lan_dryrun.py <lan-ip>
"""
import os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv = sys.argv[:2]
import ol, suite

ip = sys.argv[1]
ol.down()
relay = os.environ.get("OL_RELAY_EXE", os.path.join(HERE, "OpenOL_Relay.exe"))
rlog = os.path.join(HERE, "lan_dryrun_relay.log")
p = subprocess.Popen([relay, "--port", "7777"], cwd=os.path.dirname(relay), stdout=open(rlog, "w"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     creationflags=0x00000008 | 0x00000200)
time.sleep(2)
ol.wait_firewall(what="relay on the LAN")
with suite.IniOverride(IP=ip, UdpPort="7777"):
    log = "mp_lan.log"
    pid = int(subprocess.run(["powershell", "-NoProfile", "-Command",
        f"(Start-Process -FilePath '{ol.GAME}\\OLGame.exe' -WorkingDirectory '{ol.GAME}' -PassThru -ArgumentList 'prison_persistent?game=Multiplayer.MultiplayerGame','-nostartupmovies','-nosteam','-FORCELOGFLUSH','-log={log}').Id"],
        capture_output=True, text=True).stdout.strip())
    logp = os.path.join(ol.LOGS, log)
    for _ in range(90):
        try:
            if "Wwise(R) SDK Version" in open(logp, encoding="utf-8", errors="replace").read():
                break
        except OSError:
            pass
        time.sleep(1)
    ok = False
    for attempt in range(6):
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "olwin.py"), "wake", str(pid)], capture_output=True)
        for _ in range(15):
            ol.wait_firewall(what="game client")
            txt = open(logp, encoding="utf-8", errors="replace").read()
            if "Connected!" in txt:
                ok = True
                break
            time.sleep(1)
        if ok:
            break
    print("client log: Connected!" if ok else "client never connected", flush=True)
    print(open(rlog, encoding="utf-8", errors="replace").read()[-600:])
    time.sleep(5)
    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
p.kill()
print("done; ini restored")
