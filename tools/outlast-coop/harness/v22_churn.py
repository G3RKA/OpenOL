"""Join/leave churn on the OpenOL 2.2.0 test copy, hands-free: client 0 stays, client 1 is killed and started again N times.

  python -I v22_churn.py [<rounds>]

After every round: client 0 alive and no Critical / Assertion line in its log, the newcomer connected and in the world, and client 0 memory.
"""
import os, re, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v22
from v22_scenarios import kill, wait_for
from v22_soak import mem_mb

BAD = re.compile(r"Critical|Assertion failed|Fatal error|Unhandled Exception", re.I)


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    reg = v22.up(2, "prison_persistent")
    a, b = reg["clients"]
    time.sleep(10)
    fails = 0
    m0 = mem_mb(a["pid"])
    for r in range(1, rounds + 1):
        kill(b["pid"])
        time.sleep(4)
        b = v22.launch_client(1, "prison_persistent")
        reg["clients"][1] = b
        v22.save(reg)
        joined = wait_for(b, r"In world: cp='[^']*' persist='[^']*' epoch=\d+", 0, 90)
        okA = v22.alive(a["pid"]) and not BAD.search(v22.read_log(a["log"]))
        okB = bool(joined) and v22.alive(b["pid"]) and not BAD.search(v22.read_log(b["log"]))
        print(f"round {r}: newcomer in world {bool(joined)}, a ok {okA}, b ok {okB}, a mem {mem_mb(a['pid'])} MB", flush=True)
        fails += (not okA) + (not okB)
        time.sleep(5)
    print(f"SUMMARY rounds {rounds}, failures {fails}, client 0 memory {m0} -> {mem_mb(a['pid'])} MB", flush=True)
    v22.down()
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
