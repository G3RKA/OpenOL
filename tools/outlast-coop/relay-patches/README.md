# Relay patches (for OpenOL-Relay, commit `b9def512`)

Three patches to the source of the standalone relay (the repository `OpenOL-Relay`, directory `src`). They are plain patch files: this repository
does not contain the relay source and none of its code.

| Patch | What it does |
|---|---|
| `0001-openol-relay-trigger-radius.patch` | `--trigger-radius <units>`: a world trigger is forwarded only to players whose last known hero position is within that distance of the sender's. Unknown positions fail open; 0 (default) keeps upstream behaviour. |
| `0002-openol-relay-enemy-packet-ids.patch` | Uses the `ENEMY_*` packet ids the 2.1.0 client sends (`LOC` 0x04, door ids 0x05 to 0x08), so a player who joins while an enemy is alive gets its position in the snapshot. |
| `0003-openol-relay-drain-snapshots.patch` | The console relay's main loop never called `server_drain_snaps`, so the late-join snapshot queue (picked-up items, matinee and hero state) was never sent. One call added after `run_timeout`. |

## Build (MinGW)
```
git clone <OpenOL-Relay repository> && cd OpenOL-Relay && git checkout b9def512
patch -p1 -d src < relay-patches/0001-openol-relay-trigger-radius.patch
patch -p1 -d src < relay-patches/0002-openol-relay-enemy-packet-ids.patch
patch -p1 -d src < relay-patches/0003-openol-relay-drain-snapshots.patch
cd src && gcc -O2 -c server.c cli.c db.c && g++ -O2 main.cpp server.o cli.o db.o -o OpenOL_Relay.exe -lws2_32
OpenOL_Relay.exe --port 7777 --trigger-radius 3000
```
A fresh copy built this way reproduces the tested binary; `harness/relay_filter_test.py` (7 checks) and `harness/relay_state_test.py` (15 checks) run
against it without any game.
