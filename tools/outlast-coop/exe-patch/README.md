# Native patch: one owner for every map enemy

For `OLGame.exe` of **OpenOL 2.1.0** on Outlast Steam build 576074 (SHA-256 `2e58afbb1203d04476581f34216428d1dfc96228e5f3df8c6881323c56c93346`).
It fixes problem 5 of the write-up: map enemies are duplicated and both copies attack the same player.

## What it changes

Every client runs the AI of each map-placed enemy and sends it; every client turns what it receives into a puppet (OpenOL `EnemyChannel.cpp`,
`TickSend` and `ApplySpawn`). The patch adds one rule: when two copies of one enemy meet (same class, within 150 units), the copy of the client with
the lower player id stays real; the other client destroys its own copy and keeps the puppet. Enemies that exist on one client only are not touched.

The patch has grown since (see the sections below: data area, mailbox, shared checkpoint loads, enemy animations, story triggers from a far player); it now redirects seven sites into about 8 KB of position independent code in a new section `.olfix`. The first two sites, the enemy rule:

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

## Shared checkpoint loads and re-announcement (patches v4 and v5)

A checkpoint load (menu New Game, the F6 overlay, the mailbox) is announced to the other clients as a new world packet, `WORLD_CHECKPOINT_LOAD` (0x11, name and persistent level); the receiving client runs the same
load from its per-frame hook (a death restart on Insane difficulty is not shared, and a load that came from a partner is not sent back). Kill switch bit 2. When a client loaded after the other one had already announced its enemies,
the owner announces them again (counter `cnt_rebroadcast`).

## First-seen places (patch v6)

The merge compares the places where the two copies first appeared, not only where they stand now, so a copy that walked away before the other one appeared is still recognised as the same enemy.

## Enemy animations (patch v7)

An AI enemy that stands on a waypoint plays its idle pose through the script function `OLEnemyPawn.PlayFullBodyAnim`; OpenOL sends only the flag "animating" (bit 4 of the `LOC` flags), so a puppet never started the animation,
and with the one-owner rule the second player only has the puppet. v7 adds (kill switch bit 3):

- the owning client reads `AOLBot::CurrentAnimation` (`Bot+0x618`) when the animation really started (`Bot` bit 14 and the pawn's `bIsAnimatingFullBody`) and sends a new world packet, type 0x12:
  `[enemyLen][enemy][animLen][anim][flags: bit 0 loop, bit 1 refresh][rate][blendIn][blendOut][start][end]` (floats as raw bits; names as text, because name indexes differ between processes);
  a long animation is repeated now and then for a client that joined or reconnected;
- the receiving client queues it and its per-frame hook runs the same script function on the puppet through `ProcessEvent`; the game's own `LOC` code stops it when the flag drops;
- the puppet is spawned from its class alone, so it lacks the animation sets the level hands to the real enemy at spawn (`AdditionalAnimSets`, where the `SE_AI_*` animations live; without them the log says
  `PlayCustomAnim ..., Animation Not Found!!`). Two ways give it the sets: when our own copy is dropped in favour of the puppet it first hands its `SpawnerAnimSets` over (`AddAnimSets`; kill switch bit 4 turns this off),
  and the owner's packet also carries the full paths of its animation sets, which a puppet without sets looks up with `StaticFindObject` (counter `cnt_anim_resolved`), so an enemy that has no twin on the other client is covered too.

Measured 2026-10-28 with `harness/probe_anim.py` on two real clients: owner and puppet animate together (12 of 12 seconds on two prison checkpoints); counters `cnt_anim_sent`, `cnt_anim_recv`, `cnt_anim_played`, `cnt_anim_dropped`.
`hosttest.py` (no game) builds `olfix.c` against a fake image and engine mocks and checks the packet bytes, the queue, the FName strings and the call parameters. With the handover switched off (`probe_anim.py --disable 16`) the lookup by path alone gave 12 of 12 seconds on three checkpoints (4 lookups, no `Animation Not Found`).

## Story triggers from a player who is far away (patch v7)

OpenOL forces every trigger a player touches (`WORLD_TRIGGER_ACT`, world type 1) on every client, wherever its player stands, so the story of a player in another part of the map moves on without them
(relay patch 0001 filters this at the relay by the distance of the two heroes). The exe patch does the same on the receiving client, so it also works with the relay built into the game and with an unpatched relay:
the packet is dropped before the game sees it when the sender's last known position (`URemotePlayer.LastReceivedLoc`) is farther from the local hero than 3000 units. An unknown position, a sender the client has no position of,
and a dead or missing local hero let the trigger through. A dropped packet changes nothing locally (the trigger's `TriggerCount` is untouched), so the local player can still fire a one-shot trigger later by touching it.
Kill switch bit 5 (value 32), counters `cnt_trig_seen` and `cnt_trig_dropped`, the radius can be overridden through the data area (`trigger_r2`, squared, float bits; 0 = default). It is on by default: players who are apart no longer
pull each other through the story.

Measured 2026-10-28 with `harness/trigger_live.py` (two real clients, a scripted peer, the **upstream** relay, no mouse and no keyboard): a trigger from a peer without a known position fires on both clients, from a peer 50000 units away on none
(both clients count the drop), from a peer at the players' position on both, and with the gate switched off the far peer's trigger fires on both again. `hosttest.py` covers far, near, unknown position, unknown sender, dead hero, another packet type, a custom radius and the kill switch.

## Command mailbox (patch v3)

A per-frame hook (`AOLPlayerController::Tick`, the vtable slot +0x350 of the OLPlayerController and MultiplayerController tables, both covered by base relocations) runs commands that a test
writes into the data area: `LOAD_CHECKPOINT name [persistent level]` calls the overlay's own loader (`ExecCP`) from the game thread, outside the network poll. `harness/olmail.py <pid> load <name>` sends it;
`harness/mailbox_live.py` checks it with two clients and **no mouse and no keyboard**: both heroes moved from (3702, 4291) to the survey position of `Prison_IsolationCells01_Mid` (1979, 3481), the mailbox
answered in 0.05 s. The same-world case needs no persistent level name; a jump to another map needs it (not yet mapped).
