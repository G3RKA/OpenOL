# Outlast / OpenOL test harness (Windows, Python standard library only)

Small scripts used for the test runs in [../NOTES.md](../NOTES.md). They are game-specific helpers for OpenOL 2.1.0, not a
test suite: they start clients, observe and inject, and print what they saw. Nothing here prints PASS/FAIL yet.

**Safety:** point everything at a COPY of the game with OpenOL installed over it, and start clients with `-nosteam`
(done by `ol.py`). The owner's install, Steam Cloud saves and profile must never be touched.

## The suite

`suite.py`: `python -I suite.py [P|A|B|C|D|E|F]` (P relay protocol tests without the game; E the relay built into the shipped exe, F late join) (A prison map: connection, doors, map-enemy owner; B triggers; C enemy spawned by a player, damage, death, respawn). Starts everything, runs the tests, prints one `RESULT:` line per test and a `SUMMARY`; see
the table in [../README.md](../README.md#qa). It needs `OL_GAME_DIR`, `OL_LOG_DIR`, `OL_RELAY_EXE` and a test copy with
`OLMultiplayer.ini` pointing at the proxy (`127.0.0.1`, UDP 17778, room `PUBLIC`). Checks for game crash dialogs inside every assert.

## Protocol tools (no game needed)

| File | What it does |
|---|---|
| `relay_filter_test.py <patched.exe> <upstream.exe>` | Game-free protocol test of the relay patches: `--trigger-radius` filter with four fake peers (sender, near, far, position unknown), five checks plus a late-join enemy snapshot (T6) and twins on the upstream relay (T4, T7). ~25 s. |
| `relay_state_test.py <relay.exe>` | Game-free protocol tests of shared state: door lock exclusivity, `DOOR_INIT`/`PUSH_INIT` first-write-wins and never relayed, late-join snapshots (doors, pushables, pickups, matinee and hero state of players, gone after the owner leaves), pushable ownership and release, blind-mirror twins. ~45 s. S9 to S11 fail on the upstream relay (patch 0003). |
| `embedded_probe.py <port>` | Late-join enemy snapshot probe (fake peers, room DEFAULT) used by suite group E. |
| `pushsurvey.py <checkpoint>...` | One client: load each checkpoint, count the `PUSH_INIT` packets it sends (finds maps with pushable objects; they were only found in the male ward group). |
| `lan_dryrun.py <lan-ip>` | Dry run of the player guide on one PC: the relay started as `--port 7777` (binds `0.0.0.0`), one client with `IP=<this PC's LAN address>` and `UdpPort=7777` (ini restored); passes when the client logs `Connected!` and the relay logs the join. Needs `OL_RELAY_EXE` or `OpenOL_Relay.exe` next to the scripts. |
| `winshot.py <out.png>` | Captures only the first game window (never the desktop), for reading overlay tabs. Keep the images local. |
| `ol_menu.py <n>` | The real player path through the main menu for n clients (needs `ol.up()` first): Multiplayer > Connect (ini values), then New Game > Main > Normal. No map URL, no F6 overlay. |
| `ctl.py [-c idx] <op>...` | Real-input driver for the registered clients (walk, look, absolute yaw, keys, mouse buttons), prints the hero positions from the proxy; `shot=<name>` saves window-only pictures. |
| `soak.py <minutes>` | Idle soak of the registered clients: every 30 s process alive, hero stream fresh, memory; prints anomalies and a summary. |
| `hello_probe.py` | Sends the client's `HELLO,<room>,` line and decodes the relay reply: `python -I hello_probe.py 127.0.0.1 17777 PUBLIC=READY DEFAULT=HELLO_FAIL` |
| `relay_host.c` | 15-line `main` that runs OpenOL's embedded relay source standalone (build it with the sources from `Development/External/openol_relay`) |
| `udp_tap.py` | Logging UDP proxy between clients and a relay: `python -I udp_tap.py 17778 127.0.0.1 17777 tap.log state.json`. Decodes hero, door, enemy and world packets of the 2.1.0 wire format, logs changes (hp, enemy mode, door/trigger events, deaths) and rewrites `state.json` every 0.5 s (heroes, doors, enemies, matinees). Each client gets its own upstream socket, so the relay sees them separately. |
| `fake_peer.py` | Joins a room as a scripted third player. `trigger <path>` sends one `WORLD_TRIGGER_ACT`; `door open|close x y z` sends a `DOOR_OPEN`/`DOOR_CLOSE`; `sweep <level> <from> <to> <delay> <client_log>` sends `SeqEvent_Touch_N` triggers one by one and lists what the receiving client's log shows after each (needs the client started with `-FORCELOGFLUSH`). |
| `watch.py <seconds>` | One line per second from `state.json` (hp, special move, positions, enemy mode and distance to each hero, STALE flags). No screenshots on purpose (the repo forbids desktop capture). |

## Driving real clients (desktop input; replace with an in-game bot when possible)

| File | What it does |
|---|---|
| `ol.py` | One-command scenario driver: `up` (relay + proxy), `launch N <map>` (clients straight on a map, window wake, tiling, proxy port per client), `cp <idx> <checkpoint>` / `cpall` (checkpoint through the F6 overlay search box), `survey` (hero spawn and enemies per checkpoint), `embedded <idx> <port>` (start the relay built into the exe from the overlay), `up` also takes `relay=False` in code, `maxhp <idx> <n>` (Max Health slider), `spawn <idx>` (Soldier at the hero's feet; `attack=False` in code switches the overlay's Should Attack off), `launch N <map>` appends with `append=True` in code, `nudge <idx>` (short step), `level <idx>` (level the camera pitch), `status`, `down`. Environment: `OL_GAME_DIR`, `OL_LOG_DIR`, `OL_RELAY_EXE`, `OL_RELAY_ARGS` (extra relay arguments), `OL_UPSTREAM_RELAY_EXE` (group P twins; default `OpenOL_Relay.exe` next to the scripts), `OL_PATCHED_RELAY_EXE` (suite groups B and P: the relay built with both patches in `../relay-patches/`; default `OpenOL_Relay_patched.exe` next to the scripts, without it B3 is scored as the known upstream bug). The overlay click offsets assume the default overlay layout in a 816x639 window. Leave the overlay closed between calls. |
| `olwin.py` | Window helper: list, focus, `wake` (a client started from a background shell hangs in engine init after the Wwise log line until its window is minimized and restored), real key presses via `SendInput` (the game ignores posted key messages) |
| `goto.py`, `turn.py`, `look.py`, `hold.py`, `click.py`, `setslider.py` | Walk to x,y using the proxy's hero state with stuck detection (progress toward the target, escalating detours, `BLOCKED`, `HIT`, `STALE`), closed-loop turning, mouse look, key hold, click, ImGui slider values |

## Typical run

```
set OL_GAME_DIR=<test copy>\Binaries\Win64
set OL_LOG_DIR=<test copy>\OLGame\Logs
set OL_RELAY_EXE=<OpenOL-Relay build>\OpenOL_Relay.exe
python -I ol.py up
python -I ol.py launch 2 prison_persistent
python -I ol.py cpall Prison_OldCells_PreStruggle2
python -I ol.py status
python -I ol.py down
```

The test copy's `OLGame\Config\OLMultiplayer.ini` must point at the proxy (`IP=127.0.0.1`, `UdpPort=17778`,
`RoomCode=PUBLIC`).

## Group H (bad network) and the firewall prompt

- `suite.py H` puts the `tools/chaos` profile `bad_wifi` between the proxy and the relay (`ol.up(chaos="bad_wifi")`), then checks 90 s of connection, heroes still streaming, a door burst, a 10 s blackout (no reconnect) and a 40 s blackout (one reconnect each). About 4.5 minutes.
- The relay and the proxy bind to `127.0.0.1`, which normally avoids the Windows Firewall prompt. A new executable path that listens on all interfaces can still make Windows ask for permission. `ol.wait_firewall()` notices that window, prints `WAITING for the owner` and waits; the scripts never click it, because a firewall rule is a system security setting that only the owner changes.
- Run only the groups you touched. A full run takes about 25 minutes and is needed once before a release, not after every edit.
