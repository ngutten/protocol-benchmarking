# Stage 3: Chat, Graffiti, and NPCs

## Purpose

Extend the multi-user server so that the world feels populated and players
can leave lasting traces. Three themes run through this stage:

**Conversation.** Players in the same room can talk to each other (`say`)
and give themselves descriptions that others see on `look` (`describe me`).

**Permanence.** Players can inscribe text onto the objects around them
(`write "text" on <object>`). Unlike presence broadcasts, inscriptions and
self-descriptions persist: they are written to disk as they happen and
remain when the server restarts.

**Liveness.** Scripted NPCs inhabit the world alongside players. Each has a
starting room and a looping script of actions — saying lines, emoting,
moving between rooms. A server heartbeat advances every NPC's script one
step per tick, so the world continues to change even when no player is
acting. The tick interval is configurable on the command line; NPCs are
stateless across restarts and reset to their starting positions.

This stage does not change how clients connect or how commands look on the
wire. It adds new commands, introduces a persistence file, updates
`look <object>` to show accumulated inscriptions, extends `look <target>`
to resolve players and NPCs, and runs a background heartbeat loop.

## New commands

### `say "<text>"`

Speak a line aloud to everyone else in the current room.

Syntax:

```
say "<text>"
```

The argument MUST be wrapped in ASCII double quotes (`"`). The text between
the quotes may contain any UTF-8 characters other than a literal `"` or
newline. Leading/trailing whitespace inside the quotes is preserved as typed.

Behavior:

- Acting player sees: `You say, "<text>"` (one line).
- Every other player in the same room sees, as a broadcast:
  `<name> says, "<text>"` (one line).
- The acting player's response ends with the prompt as usual. Other players
  receive the broadcast followed by a fresh `\n> ` (same broadcast mechanism
  as Stage 2 presence events).

Error responses (to the acting player only; no broadcast fires):

| Situation | Response line |
|---|---|
| Missing quotes / malformed syntax | `Say what?` |
| Empty string (`say ""`) | `Say what?` |
| Text contains an embedded `"` | `Say what?` |

### `write "<text>" on <object>`

Append a line of player-authored text (call it an **inscription**) to an
object's description. The inscription persists across server restarts.

Syntax:

```
write "<text>" on <object>
```

The `<text>` obeys the same quoting rules as `say`. The `<object>` is
matched by the Stage 1/Stage 2 rules: inventory candidates first, then room
candidates; case-insensitive whole-string match against canonical name or
alias.

Darkness applies the same way it does to `look`/`take`/`use`: in an unlit
dark room, room-object writes produce `It is too dark to see.` (you cannot
write on something you can't see). Inventory-object writes work normally —
the player can scribble on what they hold.

Behavior on success:

- Append an inscription record to the object: the text, the author's login
  name at the time of writing, and a UTC timestamp in ISO-8601 format with
  seconds precision (e.g. `2026-04-15T17:22:03Z`).
- Persist the updated inscription list to disk (see below) BEFORE replying
  to the acting player.
- Acting player sees: `You write on the <item>.` (one line), where `<item>`
  is the object's canonical `name`.
- Every other player in the same room sees the broadcast:
  `<name> writes on the <item>.`.

Error responses:

| Situation | Response line |
|---|---|
| Missing quotes / malformed text | `Write what?` |
| Empty string | `Write what?` |
| Text contains embedded `"` | `Write what?` |
| Missing `on <object>` | `Write what?` |
| Object not visible in room or inventory (lit room) | `There is no <object> here.` |
| Target is a room object in an unlit dark room | `It is too dark to see.` |
| Target unresolved in an unlit dark room | `It is too dark to see.` |

Objects may be written on regardless of whether they are `portable`. Non-portable
objects — plaques, walls, statues — are valid targets.

### `describe me "<text>"`

Set the acting player's own description — the text other players see when
they `look` at the player. Persisted across server restarts, keyed by login
name.

Syntax:

```
describe me "<text>"
```

The `<text>` obeys the same quoting rules as `say`. The literal word `me`
MUST appear between the verb and the quoted text; no other target is
accepted at this stage.

Behavior on success:

- Persist the description to `graffiti.json` (under `players`; see schema
  below) BEFORE replying.
- Print `Your description is set.` to the acting player. No broadcast.
- An empty string (`describe me ""`) clears any existing description and
  prints `Your description is cleared.` (also persists — removing the
  player's entry from the `players` section on disk). No broadcast.

Error responses (no broadcast):

| Situation | Response line |
|---|---|
| Missing or malformed quotes | `Describe what?` |
| Text contains embedded `"` | `Describe what?` |
| Missing `me` keyword (e.g. `describe "foo"`) | `Describe what?` |
| Target other than `me` (e.g. `describe alice "foo"`) | `Describe what?` |

### Updated `look <player>`

Stage 2's generic `<name> is another adventurer.` line is replaced when the
target player has a description set. The look output for a player is:

- If the player has a description in `graffiti.json`: print the description
  as a single line, verbatim.
- Otherwise: print `<name> is another adventurer.` (the Stage 2 default).

### Target resolution order (extended)

`look <target>` now resolves candidates in this order, first match wins:

1. Inventory objects, in acquisition order.
2. Room objects, in world order (subject to the darkness rules from Stage 1).
3. NPCs in the current room, in case-insensitive alphabetical order by
   canonical name (also subject to darkness).
4. Players in the current room (including self), in case-insensitive
   alphabetical order by login name.

A hit in group 3 prints the NPC's `description` as a single line. A hit
in group 4 follows the updated `look <player>` rule above. Only after all
four groups fail does the server fall back to `There is no <target> here.`
in a lit room (or `It is too dark to see.` in a dark unlit room).

### Updated `Also here:` line

The `Also here:` line in lit room `look` output (introduced in Stage 2 as a
list of other players) now includes NPCs in the same combined list, sorted
**case-insensitively alphabetical** by canonical name (same ordering rule
as `who`). NPCs and players mix freely in the line; players distinguish
them visually by the presence of spaces (NPC canonical names may contain
spaces, player login names may not). The calling player is still excluded
from the list.

If a room contains only NPCs (no other players), the `Also here:` line is
still present and lists those NPCs. If it contains neither, the line is
absent as before.

### Updated `look <target>` (objects)

When displaying an object's description, the output is the object's
`description` field on the first line, then each inscription on its own
subsequent line, in the order they were written (oldest first). An
inscription line has this exact form:

```
Scrawled by <author>: <text>
```

Example output of `look plaque` after two inscriptions:

```
A weathered stone plaque set into the wall.
Scrawled by alice: hello from the library
Scrawled by bob: bob was here
```

An object with no inscriptions displays exactly as it did in earlier stages
(just the `description` line).

## NPCs and the heartbeat

NPCs are non-player entities defined in `assets/world.json` under a
top-level `npcs` key. Each NPC has a canonical name, optional aliases, a
description, a starting room, and a script of timed actions.

### World-file addition

```json
"npcs": {
  "<npc_id>": {
    "name": "<canonical name, possibly multi-word>",
    "aliases": ["<alias>", ...],
    "description": "<single-line description>",
    "start_room": "<room_id>",
    "script": [
      {"action": "say", "text": "..."},
      {"action": "emote", "text": "..."},
      {"action": "move", "direction": "..."},
      {"action": "wait"}
    ]
  },
  ...
}
```

- `aliases` is optional (default `[]`).
- `script` is optional (default `[]`); an empty script means the NPC does
  nothing on each tick but otherwise exists normally.
- `start_room` MUST be a room id present in the world file.
- The `npcs` top-level key may be absent entirely, in which case no NPCs
  exist and no NPC-related broadcasts ever fire.

### Starting state

On server startup (after `world.json` loads successfully), each NPC is
placed in its `start_room` and given a script index of `-1`. The first
tick advances it to `0` and executes the action at index 0.

NPC state is NOT persisted. Server restart resets every NPC to its
starting room and index `-1`. NPC position and script index are never
written to `graffiti.json` or any other file.

### Heartbeat flag

The server gains a new command-line flag:

```
python3 mudserver.py [--port N] [--tick-seconds FLOAT]
```

`--tick-seconds` defaults to `5.0`. Values must be positive floats. Tests
are expected to use smaller values (on the order of 0.2–1.0 seconds) to
exercise tick-driven behavior quickly; implementations should not impose a
lower bound.

### Tick semantics

A heartbeat fires roughly every `--tick-seconds` wallclock seconds. Ticks
and player commands are serialized through a single event queue — the
server processes one event at a time, never interleaving a tick with a
mid-flight player command. If a tick is due while a command is running,
it fires immediately after the command.

**No skipping.** Every tick that is due eventually fires. If command
processing or a slow tick has caused multiple ticks to queue up, all of
them fire (in order, each producing its own NPC advancement and its
own broadcasts) as soon as the queue drains. NPC progress over time is
therefore a pure function of wallclock seconds since server start: after
`t` seconds, every NPC has executed exactly `floor(t / tick_seconds)`
script steps. (Bursty catch-up after a load spike is the visible cost
of this guarantee.)

**No batching.** The server does not collapse a run of queued ticks into
a single combined advancement. Each tick still produces discrete
broadcasts so observers see every step.

On each tick, the server iterates NPCs in **alphabetical order by NPC id**
and processes each as follows:

1. Increment the NPC's script index by 1.
2. If the NPC's script is empty (length 0), skip this NPC.
3. Otherwise, reduce the index modulo the script length and execute the
   action at that position.

### Script actions

Each script entry has an `action` field that determines the behavior.

**`say`** — requires `text` (string).
Broadcast `<npc_name> says, "<text>"` to every player currently in the
NPC's room. `<npc_name>` is the NPC's canonical `name`. The broadcast is
delivered as a separate line on each recipient's socket, followed by a
fresh `\n> ` prompt, using the same mechanism as Stage 2 presence
broadcasts. Players in other rooms receive nothing.

**`emote`** — requires `text` (string).
Broadcast `<npc_name> <text>.` to every player in the NPC's room. If
`text` already ends in `.`, `!`, or `?`, do not append a period;
otherwise append `.`. (So both `"drifts slowly"` and `"drifts slowly."`
produce the same output, but `"Where?"` is preserved.)

**`move`** — requires `direction` (string, one of the six direction names).
- If the NPC's current room has an exit in that direction AND the exit is
  unlocked, move the NPC into the destination room.
- Broadcasts on a successful move:
  - To the room the NPC left: `<npc_name> leaves to the <direction>.`
  - To the room the NPC entered: `<npc_name> arrives from the <opposite>.`
    where `<opposite>` uses the same direction-opposite rule as player
    movement (`north`↔`south`, `east`↔`west`, `up`↔`down`). If the entered
    room has no exit in the opposite direction back to the previous room,
    the line instead reads `<npc_name> arrives.`.
- If the exit is missing, or the direction is not one of the six valid
  names, or the exit is locked: the action is skipped silently. No
  movement, no broadcast. The script index still advances (the tick is
  consumed).

**`wait`** — no fields.
Do nothing this tick. Used for pacing the script.

Unknown action types in a script should be treated as `wait` (silently
ignored). Do not crash the server.

### NPC interactions with other features

- Dark rooms: NPCs in a dark unlit room do not appear in the (suppressed)
  `Also here:` line. Their `say` and `emote` broadcasts still reach any
  players present — speech is audible even in the dark. A `move` into or
  out of a dark room still fires the leave/arrive broadcasts normally.
- Locked exits: NPCs cannot unlock anything. A `move` action through a
  locked exit is a silent no-op.
- Player `say`: players do not receive responses from NPCs; NPC scripts
  do not react to player text. The two systems run independently.
- `write "..." on <npc>`: NPCs are not valid write targets; fall through
  to `There is no <target> here.`.
- `who`: lists logged-in players only, not NPCs.

## Persistence

### File: `graffiti.json`

Inscriptions are stored in a file called `graffiti.json` at the current
working directory (NOT inside `assets/` — the world data in `assets/` is
treated as read-only and shipped-with-the-task; `graffiti.json` is
runtime-authored state that lives at the workspace root). The server creates
this file the first time an inscription is written. If the file does not
exist at startup, the server treats every object as having zero inscriptions.

### Schema

```json
{
  "version": 1,
  "objects": {
    "<object_id>": [
      {"author": "<name>", "text": "<text>", "timestamp": "<ISO-8601 UTC>"},
      ...
    ],
    ...
  },
  "players": {
    "<player_name>": "<description text>",
    ...
  }
}
```

- Keys of `objects` are the object ids from the world file.
- Each inscription value is a list, in write order.
- `timestamp` is UTC, ISO-8601 with `Z` suffix, seconds precision
  (no fractional seconds).
- Keys of `players` are login names (case-sensitive, as established at login).
  Values are the player's `describe me` text. A player with no description
  set has no entry in this map.
- Both `objects` and `players` are optional at the top level; either or both
  may be absent (treated as empty). A fresh `graffiti.json` with only
  inscriptions omits the `players` key; one with only descriptions omits
  `objects`.
- `version` is the integer `1`. If the file exists but `version` differs
  from `1`, the server writes `Error: unsupported graffiti.json version` to
  stderr and exits non-zero.

### Write durability

Every successful `write` and `describe me` command updates `graffiti.json`
before the server responds to the player. Use a safe write pattern: write
the full new contents to `graffiti.json.tmp` in the same directory, `fsync`
if possible, then atomically rename to `graffiti.json`. A crash mid-write
must never leave the file empty or half-written.

### Load behavior

On startup (after successfully loading `assets/world.json`):

- If `graffiti.json` does not exist, treat all objects as having no
  inscriptions.
- If it exists and is valid, each object id in the file gets its inscription
  list attached.
- If the file references an object id not present in `world.json`, ignore
  that entry (do NOT fail startup; the world may have changed).
- If the file is malformed (not JSON, missing required fields, wrong
  version), write `Error: malformed graffiti.json` to stderr and exit
  non-zero.

## Author name behavior

- The `author` field in each inscription is the login name the player was
  using at the time of writing.
- If that player later disconnects and reconnects under a different name,
  existing inscriptions keep the original author.
- Two different sessions over the server's lifetime may end up listed as
  authors of different inscriptions on the same object; this is expected.

## Broadcast table (additions)

| Event | Recipients | Broadcast line |
|---|---|---|
| Player successfully runs `say "<text>"` | Everyone else in the same room | `<name> says, "<text>"` |
| Player successfully runs `write "<text>" on <object>` | Everyone else in the same room | `<name> writes on the <item>.` |
| NPC tick action `say` | Every player in the NPC's current room | `<npc_name> says, "<text>"` |
| NPC tick action `emote` | Every player in the NPC's current room | `<npc_name> <text>.` (period appended unless text already ends in `.`, `!`, or `?`) |
| NPC tick action `move` (successful) | Players in the room the NPC left | `<npc_name> leaves to the <direction>.` |
| NPC tick action `move` (successful) | Players in the room the NPC entered | `<npc_name> arrives from the <opposite>.` (or `<npc_name> arrives.` if no back-exit) |

Failed `say` and `write` commands (bad syntax, unmatched object) produce no
broadcast. Player `describe me` never broadcasts. Failed NPC moves (blocked
or missing exit) produce no broadcast.

## Unchanged behavior

- All Stage 1 commands and their response strings are unchanged.
- All Stage 2 commands, presence broadcasts, login handshake, `who`, `quit`,
  disconnect handling, and concurrency guarantees are unchanged.
- `assets/world.json` is still read-only at runtime. The server never writes to it.
- Objects that have been consumed (via `use` with `consumed: true`) cannot be
  written on — they no longer exist. If a player tries, the response is
  `There is no <object> here.`.

## Summary of deliverables

- `mudserver.py` — updated to implement `say`, `write`, `describe me`,
  updated `look` (inscriptions, player descriptions, NPC targeting),
  persistence, and the NPC heartbeat. Accepts the new `--tick-seconds
  FLOAT` flag in addition to Stage 2's flags.
- `mudclient.py` — unchanged from the previous stage (it only forwards bytes;
  no protocol-level changes are needed in the client).
- `graffiti.json` — not shipped; created and maintained by the server at
  runtime. Must be absent from the initial workspace.
- `assets/world.json` — extended with an `npcs` top-level section.
