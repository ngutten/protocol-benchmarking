# Text Adventure Engine → Multi-User Server

## Overview

This project builds up, over three stages, from a single-player text adventure game
into a concurrent multi-user server with persistent player-authored content. The
arc is deliberately refactor-heavy: each stage asks for a significant restructuring
rather than a purely additive feature. A competent implementation of Stage 1 is
unlikely to be the right internal shape for Stage 2, and the Stage 2 server will
need further surgery to absorb Stage 3's new semantics.

Stage 1 is a standalone, interactive command-line game that a human can actually
play. Stage 2 splits it into a server and a thin client, and makes the server
multi-user. Stage 3 extends the server with player-to-player messaging and
persistent world modifications authored by players at runtime.

The language is Python 3 (standard library only, no third-party dependencies).
The test harness exercises the system either through stdin/stdout (Stage 1) or
through raw TCP (Stage 2 and later), so implementation details like thread-vs-
asyncio are up to the implementer, but the wire protocol and message formats
are tightly specified below.

## The World File

All three stages load world data from a file named `assets/world.json`,
relative to the current working directory. The model does NOT author world
content; a canonical `assets/world.json` ships with the task, and test suites
may substitute their own.

### Schema

```json
{
  "start": "foyer",
  "rooms": {
    "foyer": {
      "name": "Foyer",
      "description": "A dusty foyer. Marble floors are cracked under your feet.",
      "exits": {"east": "library", "north": "garden"},
      "objects": ["brass_lantern", "rusted_key"]
    },
    "library": { ... }
  },
  "objects": {
    "brass_lantern": {
      "name": "brass lantern",
      "aliases": ["lantern", "lamp"],
      "description": "A tarnished brass lantern, cold to the touch.",
      "portable": true,
      "use_effect": {"message": "The lantern flickers to life.", "consumed": false}
    },
    "health_potion": {
      "name": "health potion",
      "aliases": ["potion", "vial"],
      "description": "A small glass vial of dark red liquid.",
      "portable": true,
      "use_effect": {"message": "You feel refreshed.", "consumed": true}
    },
    "stone_plaque": {
      "name": "stone plaque",
      "aliases": ["plaque"],
      "description": "A weathered stone plaque set into the wall.",
      "portable": false
    }
  }
}
```

### Field semantics

- `start` (string): the room id where new players spawn.
- `rooms` (object): map of room id → room definition.
  - `name` (string): displayed as the room title.
  - `description` (string): displayed as the room body text. Single line (no `\n`).
  - `dark` (boolean, optional): if true, the room is dark and requires a lit
    light source to see in. Default: `false`. See "Darkness and Light" below.
  - `dark_description` (string, optional): shown instead of `description`
    when the room is dark and unlit. Required iff `dark` is true.
  - `exits` (object): map of direction name → exit spec. A value may be either
    a string (the destination room id, for a simple exit) or an object with
    `room` (destination id), `locked_by` (object id that unlocks it), and
    `locked_message` (string shown when the exit is tried while locked).
    Directions are among `north`, `south`, `east`, `west`, `up`, `down`.
  - `objects` (array of strings): object ids initially present in the room.
- `objects` (object): map of object id → object definition.
  - `name` (string): the canonical name shown to players. Matched case-insensitively.
  - `aliases` (array of strings, optional): additional names that match this object.
    Matched case-insensitively. Default: `[]`.
  - `description` (string): displayed on `look <object>`. Single line.
  - `portable` (boolean): whether `take` can pick it up.
  - `use_effect` (object, optional): see command semantics below.
  - `toggle` (object, optional): makes the object a two-state toggle (on/off)
    flipped by `use`. Fields: `initial` (`"on"` or `"off"`),
    `on_message` (shown when flipped on), `off_message` (shown when flipped off).
    An object with a `toggle` field should NOT have a `use_effect` field.
  - `light` (boolean, optional): when true, the object emits light whenever
    its toggle state is `on` (or always, if it has no toggle). Default: `false`.

Object ids appear in exactly one location at startup (in a room's `objects`
list or — via future player actions — an inventory). The world file should not
list the same object id in two rooms simultaneously.

The world file may also define `npcs` (a top-level object keyed by NPC id):

- `name` (string): canonical display name, case-insensitive for matching.
- `aliases` (array of strings, optional): additional names that match.
- `description` (string): shown on `look <npc>`. Single line.
- `start_room` (string): room id where the NPC begins.
- `script` (array, optional): list of tick actions (see "NPCs and the
  Heartbeat" below). May be empty or absent, in which case the NPC stands
  still and does nothing.

NPCs are introduced in Stage 3. The `npcs` key may be absent entirely from
a world file; tests and earlier stages may use worlds without NPCs.

## Command and Response Conventions

All three stages share a common interaction pattern, even though the transport
differs. The rules below apply wherever a human or client sends text to the
game and receives text back.

### Input

- One command per line, terminated by `\n`.
- Empty input (just `\n`) is valid and produces no response body (see prompt
  behavior below).
- Commands and object names are case-insensitive.
- Leading and trailing whitespace on an input line is stripped before parsing.
- Multiple spaces between tokens are collapsed to a single space.

### Output

- Each command produces zero or more **response lines**, each terminated by `\n`.
- After the response lines, the server writes a **prompt** consisting of the
  two ASCII bytes `> ` (greater-than, space) with **no trailing newline**,
  and flushes. The prompt signals that the server is ready for the next command.
- A response with zero body lines (for example, empty input) produces just the
  prompt.
- At startup, the server emits a short welcome banner, then the description of
  the starting room in `look` format, then the prompt.

### Reading responses (for test clients)

Read bytes from the stream until the buffer ends with `> ` (the prompt). The
text preceding that marker is the response body. This convention is identical
on stdin/stdout (Stage 1) and on TCP (Stage 2+).

## Command Vocabulary

Stage 1 introduces the base vocabulary. Later stages extend it; see stage files
for additions.

| Command | Effect |
|---|---|
| `look` (or `l`) | Describe the current room. |
| `look <target>` (or `l <target>`) | Describe an object visible in the current room or in inventory. |
| `go <direction>` | Move to the room connected by that exit. |
| `<direction>` (bare) | Shorthand for `go <direction>`. |
| `n`, `s`, `e`, `w`, `u`, `d` | Shorthand for `go north` etc. |
| `take <object>` (or `get <object>`) | Pick up a portable object in the current room. |
| `drop <object>` | Move an object from inventory to the current room. |
| `use <object>` | Trigger the object's use-effect, toggle its state, or unlock a matching exit. |
| `inventory`, `i` | List what the player is carrying. |
| `help` | Print the command list. |
| `quit` | End the session. |

Shortcuts are normalized to their canonical form before any other processing.
A shortcut behaves exactly like its full form; e.g. `get` given without an
argument is equivalent to `take` given without an argument, and produces
`I don't understand that.` in both cases.

## Room Description Format (`look`)

The room display has this exact structure:

```
<room name>
<room description>
Exits: <comma-separated direction names, sorted alphabetically>
You see: <comma-separated object names, in world order>
```

Rules:
- Line 1: room `name` verbatim.
- Line 2: room `description` verbatim.
- Line 3: always present. If no exits, the line reads exactly `Exits: none`.
  Otherwise the directions are listed comma-separated (", ") in alphabetical
  order.
- Line 4: present **only if** the room contains at least one object. Objects
  are listed by canonical `name`, comma-separated (", "), in the order they
  appear in the room's object list (initial world order, with dropped/added
  objects appended in the order events occurred).

## Object Name Matching

When a command takes an object argument, the argument text (after case-folding
and whitespace collapse) is matched against each candidate's `name` and
`aliases` using **exact equality** (no prefix matching). Candidates are the
objects visible to the player (in the current room plus, for commands that
apply to carried items, the inventory).

If multiple candidates match, the first match wins in this order:
1. Inventory objects, in the order they were acquired.
2. Room objects, in world order.

## Standard Response Strings

Commands that do not produce descriptive output use fixed strings. Tests assert
on these verbatim.

| Situation | Response line |
|---|---|
| Successful `take` | `Taken.` |
| Successful `drop` | `Dropped.` |
| Object not present for `take` | `There is no <name> here.` |
| Object not portable | `You can't take the <name>.` |
| Object not in inventory for `drop` | `You don't have the <name>.` |
| Object not present for `use` | `There is no <name> here.` |
| `use` on object with no effect | `Nothing happens.` |
| `go` into a nonexistent exit | `You can't go that way.` |
| `go` into a locked exit | the exit's `locked_message` (single line) |
| `use <key>` unlocking one or more exits in the current room | one line per unlocked direction: `You unlock the way <direction>.` (directions in alphabetical order) |
| Targeting a room object while in an unlit dark room | `It is too dark to see.` |
| Empty inventory | `You are carrying nothing.` |
| Non-empty inventory | `You are carrying: <names>` (comma-separated, acquisition order) |
| Unknown command | `I don't understand that.` |
| `quit` | `Goodbye.` on its own line (no trailing prompt), then the session ends — the process exits (Stage 1) or the TCP connection closes (Stage 2+) |

`<name>` in these strings is the object's canonical `name` field (never an alias),
except for the `There is no <name> here.` and `You don't have the <name>.`
forms when no object was matched — in those cases, `<name>` is the user's
input text, lowercased and whitespace-collapsed.

### `use` semantics

`use <object>` applies to objects visible in the current room or in the
player's inventory. The behavior is determined by the object's definition,
evaluated in this order:

1. **Unlocking a locked exit.** If the current room has one or more locked
   exits whose `locked_by` equals this object's id, every such exit is
   unlocked. For each unlocked direction (alphabetical order) the server
   prints `You unlock the way <direction>.`. The key is NOT consumed. This
   takes precedence over toggle/use_effect: a key with a `use_effect` used in
   a room with a matching lock unlocks rather than triggering its use_effect.
2. **Toggle.** If the object has a `toggle` field (and did not unlock
   anything above), flip its state. Print `on_message` if the new state is
   `on`, `off_message` if `off`. Toggle state persists on the object
   regardless of whether the object is in the room or in an inventory.
3. **Use-effect.** If the object has a `use_effect`, print the effect's
   `message`. If `consumed: true`, remove the object from wherever it was.
   A consumed object no longer exists in the game state.
4. **No effect.** If none of the above apply, print `Nothing happens.`

## Darkness and Light

Rooms with `dark: true` are dark by default. A dark room becomes lit only if
a **lit light source** is present — that is, an object with `light: true`
whose current toggle state is `on` (an object with `light: true` but no
toggle is always emitting light). The light source counts if it is in the
room's object list OR in a player's inventory, provided that player is in
the room. Lighting is a property of the room itself: if a light source
qualifies, everyone observing the room sees it as lit.

Effects of being in an unlit dark room:

- `look` shows only the room `name` on line 1 and the `dark_description` on
  line 2. No `Exits:` line, no `Also here:` line, no `You see:` line.
- `look <target>` where target is a room object: `It is too dark to see.`
- `look <target>` where target is an inventory object: works normally
  (the player can feel what they carry).
- `take <target>`: `It is too dark to see.` — regardless of whether the
  object exists in the room.
- `use <target>` where target is a room object: `It is too dark to see.`
- `use <target>` where target is an inventory object: works normally. (This
  is how the player lights a lantern they're carrying.)
- `drop <target>`: works normally.
- `go <direction>`: works normally. Movement is not blocked by darkness,
  but locked exits are still locked.

Evaluation is instantaneous: if a player in a dark room lights a lantern in
their inventory, the same room description (now lit) will be produced by the
next `look`.

## Toggle Objects

An object with a `toggle` field has two states, `on` and `off`, beginning at
`initial`. `use <object>` flips the state and prints the appropriate
message. The `toggle` field may coexist with `light` (giving you a
turn-on-to-illuminate light source) but not with `use_effect`.

Toggle state is part of world state: it persists across pickups, drops, and
(for Stage 2+) remains visible to all players. It is NOT part of the
shipped world file — states begin at `initial` on every server start and
reset when the server restarts.

## Locked Exits

An exit may be specified as an object with `room`, `locked_by`, and
`locked_message`. Initially the exit is locked; `go <direction>` through it
prints the `locked_message` (as a single response line) without moving the
player. Broadcasts do not fire for failed movement.

A locked exit can be unlocked by using the matching key object (see `use`
semantics above). Once unlocked, the exit behaves as a simple exit for the
remainder of the server's lifetime. Re-locking is not supported.

## NPCs and the Heartbeat

NPCs are introduced in Stage 3. An NPC is a non-player entity with a
position, a description, and a scripted behavior loop driven by a server
heartbeat. NPCs never hold inventory, cannot be taken or dropped, do not
appear in `who`, and do not respond to player speech — they simply execute
their script.

### Where NPCs appear

- An NPC occupies exactly one room at a time. At server start, NPCs are
  placed at their `start_room` and at script index -1 (the first tick
  advances to index 0).
- In a lit room's `look` output, NPCs are listed in the `Also here:` line
  alongside other players. The combined list is sorted alphabetically by
  canonical name, **case-insensitively** (the same case-folded ordering
  used by `who`); ties broken by the original case-preserving form. The
  calling player is still excluded from this line.
- NPCs do not appear in room output when the room is dark and unlit (the
  `Also here:` line is absent under those conditions).
- `look <npc_name>` returns the NPC's `description` as a single line. In
  dark unlit rooms, `look <npc_name>` produces `It is too dark to see.`.
- `take`, `drop`, `use`, and `write` do not match NPCs; they fall through
  to `There is no <target> here.` (or the dark-room equivalent).

### Heartbeat cadence

The server runs a heartbeat at a wallclock interval configured by a
command-line flag:

```
python3 mudserver.py [--port N] [--tick-seconds FLOAT]
```

Default: `--tick-seconds 5.0`. Must be a positive float. Tests are expected
to set this to a smaller value for fast iteration; implementations should
not bake in a minimum.

Ticks and player-command processing are serialized on a single event queue:
at any moment, either a tick or a player command is being processed, never
both. If a tick is due while a command is being processed, it fires
immediately after. Under sustained load (multiple ticks queued behind
commands or behind a slow tick), every queued tick eventually fires in
order — no skipping — but each tick still produces its own discrete
NPC advancement and broadcasts — no batching. NPC progress is therefore
a pure function of wallclock time since server start: after `t` seconds,
every NPC has executed exactly `floor(t / tick_seconds)` script steps.
Bursty catch-up after a load spike is the visible cost of that
determinism guarantee.

### Per-tick behavior

On each tick, the server iterates NPCs in **alphabetical order by NPC id**
and advances each one:

1. Increment the NPC's script index by 1.
2. If the script is empty, skip.
3. Otherwise, wrap the index modulo the script length and execute the
   action at the new index.

### Script actions

Each script entry is an object with an `action` field and action-specific
data.

| Action | Fields | Effect |
|---|---|---|
| `say` | `text` (string) | Broadcast `<name> says, "<text>"` to every player in the NPC's current room. `<name>` is the NPC's canonical name. |
| `emote` | `text` (string) | Broadcast `<name> <text>.` to every player in the NPC's current room. A period is appended if `text` does not already end in one. |
| `move` | `direction` (string) | If the NPC's current room has an unlocked exit in that direction, move the NPC into the destination room. Fire presence broadcasts: `<name> leaves to the <direction>.` in the room left, and `<name> arrives from the <direction>.` in the room entered (with the same direction-opposite rule players use; if no back-exit, the arrival line is `<name> arrives.`). If the exit is missing or locked, the action is skipped with no broadcast. |
| `wait` | — | No effect this tick. |

NPC broadcasts reach every player currently in the relevant room,
including new arrivals who enter between ticks. NPC script state resets
on server restart (position returns to `start_room`, index returns to -1).

## Stage 1: Single-Player Interactive Game

See `stages/01_single_player.md`. Summary: a standalone Python program
(`mud.py`) that runs as an interactive loop on stdin/stdout. One player, one
process, no networking.

## Stage 2: Client/Server Split and Multi-User Server

See `stages/02_client_server.md`. Summary: refactor into `mudserver.py` (a
TCP server that accepts multiple concurrent clients, each controlling their
own character in a shared world) and `mudclient.py` (a thin TUI that
reproduces Stage 1's user-facing experience over TCP).

Additions introduced at Stage 2:
- Login: the first line a client sends is `login <name>`. Names are unique.
- Presence broadcasts in shared rooms when players arrive, leave, take, drop,
  or use objects.
- `who` command.
- Fixed broadcast phrasings (see the Stage 2 spec).

## Stage 3: Chat, Graffiti, and NPCs

See `stages/03_chat_and_graffiti.md`. Summary: extend the server with
player-to-player messaging (`say`), player-authored persistent additions to
object descriptions (`write "text" on <object>`), player self-descriptions
(`describe me`), a restart-safe persistence layer (`graffiti.json`), and
scripted NPCs driven by a wallclock heartbeat.

## Out-of-Scope

Across all three stages, the following are explicitly NOT required:
- Authentication beyond unique names.
- TLS / encryption.
- Rate limiting.
- Combat, quests, NPC dialog parsing, NPC reaction to player speech.
- Object containers (putting things inside other things).
- Prefix-based object name matching.
