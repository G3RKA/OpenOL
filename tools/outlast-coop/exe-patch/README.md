# Native patch: one owner for every map enemy

For `OLGame.exe` of **OpenOL 2.1.0** on Outlast Steam build 576074 (SHA-256 `2e58afbb1203d04476581f34216428d1dfc96228e5f3df8c6881323c56c93346`).
It fixes problem 5 of the write-up: map enemies are duplicated and both copies attack the same player.

## What it changes

Every client runs the AI of each map-placed enemy and sends it; every client turns what it receives into a puppet (OpenOL `EnemyChannel.cpp`,
`TickSend` and `ApplySpawn`). The patch adds one rule: when two copies of one enemy meet (same class, within 150 units), the copy of the client with
the lower player id stays real; the other client destroys its own copy and keeps the puppet. Enemies that exist on one client only are not touched.

Two call sites in the exe are redirected to `olfix.c` (about 1 KB of position independent code in a new section `.olfix`):

| Site (RVA) | Original | Hook | Rule |
|---|---|---|---|
| `0x172B0B4` in `UEnemyChannel::OnBinaryPacket` | `call ApplySpawn` | `my_ApplySpawn` | after the puppet is made: our enemy of that class is at its place -> sender id lower: destroy ours; higher: destroy the puppet |
| `0x1736CAB` in `UEnemyChannel::TickSend` | `call [rax+0x268]` (`SendSpawn`) | `my_SendSpawn` | before announcing our enemy: a puppet of that class is at its place -> owner id lower: destroy ours, announce nothing; higher: destroy the puppet |

Addresses and field offsets were found with Ghidra 12.1.4 (scripts in `ghidra/`) from the strings and the structure of OpenOL's own public
multiplayer source; no Outlast source was used. The code reads the image base from the PEB, so ASLR does not matter, and it has no imports.

## Use

```
python -I build.py                                   # optional: rebuild olfix.json from olfix.c (MinGW gcc); the committed olfix.json is the build used in the tests
python -I apply_patch.py <game copy>\Binaries\Win64\OLGame.exe OLGame_patched.exe
```
`apply_patch.py` never writes to its input and refuses any file with another SHA-256. Keep the original exe; put the patched one in its place in a
**copy** of the game. Every player of a session should use the patched exe (an unpatched client keeps its duplicates on its own side).

## Tests (harness `suite.py`, group A; the suite notices the `.olfix` section and expects the fix)

| Check | Patched exe | Original exe (twin) |
|---|---|---|
| A4 map enemy has one owner (both clients load the checkpoint, lower id first) | PASS | XFAIL, 1 spot with patients sent by both clients |
| A4b the same when the higher id loads first | PASS | XFAIL, 1 spot sent by both |
| A4c both game processes alive after the handover | PASS | PASS |

Not tested yet: a scripted story enemy that the story waits for (the destroyed copy may stall a script on the higher-id client), enemies of one class
standing closer than 150 units to each other, three players, two PCs.

## Patch tooling (v2 layout)

- `sites.json` is the one table of what is patched: the input SHA-256, the reference output SHA-256, the new section (name, RVA, size of an optional zeroed data area that makes the
  section writable) and the list of sites (`call32`: a direct call, `call_vt6`: a 6-byte virtual call turned into a direct call plus a nop, `vtable_slot`: an absolute pointer),
  each with the bytes that must be there before it is touched.
- `build.py` compiles `olfix.c` and writes `olfix.json` (code, entry offsets and the table). `apply_patch.py` and `play/apply-native-patch.ps1` both read only `olfix.json`.
- `selftest.py <original OLGame.exe>` is a static test with no game: reference hash, only the allowed bytes changed, every site decodes to its entry, characteristics, and three
  refusals. The two appliers produce identical bytes (checked for the plain section and for the section with a data area).

## Data area, kill switch and counters (patch v2)

The section also carries a zeroed, writable data area (`sites.json` `layout`): a kill switch per feature (bit 0 = the one-owner rule, a SET bit switches it off) and counters (hook calls,
own enemies destroyed as duplicates, puppets destroyed). `harness/olmail.py` reads and sets them from outside with `ReadProcessMemory` and `WriteProcessMemory` on the game's
own process, so a test switches the rule off and on **inside one run** instead of swapping the exe: `harness/twin_live.py` does it (rule on: one enemy in total, the merge counters
move; rule off: every client has its own copy and a puppet, the original bug). Measured 2026-10-22: rule on `own [1, 0] puppets [0, 1]`, rule off `own [1, 1] puppets [1, 1]`.
