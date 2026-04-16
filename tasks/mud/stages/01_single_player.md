# Stage 1: Single-Player Text Adventure

## Purpose

Build a small text adventure game that a person can sit down at and play on
the command line. The program presents a prompt, accepts typed commands like
`look`, `go east`, `take lantern`, and `use potion`, and prints short
descriptive text in response. A player walks between rooms, picks up objects,
carries them around, drops them elsewhere, and triggers simple use-effects
(drinking a potion, lighting a lantern). The world — its rooms, connections,
objects, and descriptions — is not hard-coded; it is loaded at startup from a
JSON file, so the same engine can run any world you hand it.

There is one player and one process. Input comes from standard input, output
goes to standard output. No network, no files written back to disk, no saved
games.

## Entry point

Create a program `mud.py` in the workspace. It is invoked as:

```
python3 mud.py
```

On startup, the program reads `assets/world.json` (a path relative to the
current working directory). If the file is missing or malformed, the program
prints a single line to standard error beginning with `Error:` and exits with
a non-zero status.

## World file

`assets/world.json` describes the map and the objects in it. The schema is:

```json
{
  "start": "foyer",
  "rooms": {
    "<room_id>": {
      "name": "<displayed name>",
      "description": "<displayed body text, single line>",
      "dark": false,
      "dark_description": "<shown when the room is dark and unlit>",
      "exits": {
        "<direction>": "<destination_room_id>",
        "<direction>": {
          "room": "<destination_room_id>",
          "locked_by": "<object_id>",
          "locked_message": "<shown when the player tries to go through while locked>"
        }
      },
      "objects": ["<object_id>", ...]
    },
    ...
  },
  "objects": {
    "<object_id>": {
      "name": "<canonical name>",
      "aliases": ["<alias>", ...],
      "description": "<displayed on look, single line>",
      "portable": true,
      "use_effect": {"message": "<text>", "consumed": false},
      "toggle": {"initial": "off", "on_message": "<text>", "off_message": "<text>"},
      "light": false
    },
    ...
  }
}
```

Notes:
- `start` is the room id where the player begins.
- Exit direction names are drawn from `north`, `south`, `east`, `west`, `up`, `down`.
- An exit value is either a string (the destination room id) or an object
  with `room`, `locked_by`, and `locked_message`.
- `aliases` is optional; default is `[]`.
- `dark` is optional; default is `false`. If `dark` is `true`,
  `dark_description` must also be present.
- `use_effect` is optional. Default: no effect.
- `toggle` is optional. When present, the object is a two-state toggle
  (`on`/`off`) flipped by `use`. `toggle` and `use_effect` are mutually
  exclusive on the same object.
- `light` is optional; default is `false`. An object with `light: true`
  emits light whenever its toggle is `on` (or at all times, if it has no
  toggle).
- Object ids are unique and appear in at most one room's `objects` list at
  startup.

## Interaction protocol

The program writes text to stdout and reads commands from stdin, one command
per line.

### Response format

Each command produces zero or more response lines (each ending in `\n`),
followed by a **prompt** consisting of the two bytes `> ` (greater-than,
space) with NO trailing newline. The prompt indicates the program is ready
for the next command. Output is flushed after every response.

A human playing the game sees something like:

```
Welcome.

Foyer
A dusty foyer. Marble floors are cracked under your feet.
Exits: east, north
You see: brass lantern, rusted key
> take lantern
Taken.
> go east
Library
Tall shelves loom in the gloom.
Exits: west
>
```

(The final `>` above has no trailing newline; the cursor sits right after it.)

### Startup banner

On startup, after the world file is loaded successfully, the program writes:

1. The line `Welcome.`
2. A blank line (i.e. `\n`).
3. The starting room's description in `look` format (see below).
4. The prompt `> `.

### Empty input

If the player hits Enter without typing anything, the program produces no
response lines and simply reprints the prompt.

### Input normalization

Before parsing, an input line is stripped of leading and trailing whitespace,
internal runs of whitespace are collapsed to single spaces, and the whole line
is lowercased for keyword matching. Object-name arguments are also lowercased
for comparison against names and aliases (which are compared case-insensitively).

### Command aliases

Certain verbs have short aliases that are normalized to the canonical verb
before any other processing. An alias behaves exactly like its canonical form.

| Canonical | Aliases |
|---|---|
| `look` | `l` |
| `take` | `get` |
| `inventory` | `i` |
| `go north` | `north`, `n` |
| `go south` | `south`, `s` |
| `go east` | `east`, `e` |
| `go west` | `west`, `w` |
| `go up` | `up`, `u` |
| `go down` | `down`, `d` |

`look` / `l` takes an optional target; all other aliases follow the same
argument rules as their canonical forms.

## Commands

### `look`

If the current room is lit (either not `dark`, or `dark` with at least one
lit light source in the room — listed directly in the room's objects or in
a player's inventory, as long as that player is in the room), print in this
exact format:

```
<room name>
<room description>
Exits: <directions>
You see: <objects>
```

- Line 1: the room's `name` field, verbatim.
- Line 2: the room's `description` field, verbatim.
- Line 3: always present (in a lit room). If the room has no exits, the
  line is exactly `Exits: none`. Otherwise it is `Exits: ` followed by the
  exit direction names comma-separated with `, ` (ASCII `,` then space), in
  alphabetical order. Locked exits are still listed by direction, with no
  annotation.
- Line 4: present only if the room currently contains at least one object.
  It is `You see: ` followed by object canonical names, comma-separated with
  `, `, in **world order** — the order they appear in the room's object list.
  When the player drops an object into a room, it is appended to the end of
  that list.

If the current room is dark and unlit, print only:

```
<room name>
<dark_description>
```

Two lines. No `Exits:` line. No `You see:` line. See the "Darkness and
Light" section below.

### `look <target>`

Resolve the target against objects in the current room plus the player's
inventory. Matching rule: target text is matched case-insensitively,
whole-string, against each candidate's canonical `name` and each of its
`aliases`. When multiple candidates match, prefer in this order:

1. Inventory objects, in the order they were acquired.
2. Room objects, in world order.

If the current room is dark and unlit:
- Inventory matches produce the object's `description` as usual.
- A match against a room object produces `It is too dark to see.`.
- No match at all produces `It is too dark to see.` (the player cannot tell
  what's there).

If the current room is lit:
- A match prints the object's `description` as a single line.
- No match prints `There is no <target> here.`, where `<target>` is the
  user's normalized input text.

### `go <direction>` (and direction shortcuts)

If the current room has an exit in the requested direction:
- If the exit is locked, print the exit's `locked_message` as a single line.
  The player does not move.
- If the exit is unlocked (or was never locked), move the player into the
  destination room and print the destination's `look` output.

If the current room has no exit in the requested direction (or the direction
name is not among `north`, `south`, `east`, `west`, `up`, `down`), print
exactly:

```
You can't go that way.
```

Movement works the same way in dark rooms as in lit rooms. The
`locked_message` and `You can't go that way.` lines are the only failure
outcomes; a failed `go` never produces the destination's `look` output.

### `take <object>` (alias `get <object>`)

If the current room is dark and unlit, print `It is too dark to see.` and
do nothing.

Otherwise, match the target against objects in the current room. If no match:
print `There is no <target> here.` (with `<target>` being the user's
normalized input). If the matched object's `portable` is false: print
`You can't take the <name>.` (with `<name>` being the object's canonical
name). Otherwise: remove the object from the room, append it to the player's
inventory in acquisition order, and print `Taken.`.

### `drop <object>`

Match the target against objects in the player's inventory only. If no match:
print `You don't have the <target>.` (with `<target>` being the user's
normalized input). Otherwise: remove the object from inventory, append it to
the current room's object list, and print `Dropped.`.

### `use <object>`

Resolve the target against the player's inventory first, then the current
room, using the same ordering rule as `look <target>`.

Targeting rules in dark rooms:
- An inventory match is always allowed (the player can act on what they
  hold), even in unlit darkness.
- A room-object match in an unlit dark room produces `It is too dark to see.`.
- No match at all in an unlit dark room produces `It is too dark to see.`.
- In lit rooms, no match produces `There is no <target> here.`.

Once a target is resolved, behavior is determined in this priority order:

1. **Unlock.** If one or more exits of the current room have `locked_by`
   equal to this object's id, every such exit becomes unlocked. For each
   direction unlocked (alphabetical order), print
   `You unlock the way <direction>.` on its own line. The key object is
   NOT consumed. This rule takes priority over toggle and use_effect.
2. **Toggle.** Otherwise, if the object has a `toggle` field, flip its
   state. Print `on_message` when the new state is `on`, `off_message`
   when `off`. The object is not consumed. Toggle state persists across
   pickups and drops.
3. **Use-effect.** Otherwise, if the object has a `use_effect`, print the
   effect's `message` on a single line. If `consumed: true`, remove the
   object from wherever it was (inventory or room). A consumed object no
   longer exists.
4. **Nothing.** Otherwise, print `Nothing happens.`.

### `inventory` / `i`

If the player is carrying nothing, print `You are carrying nothing.`.
Otherwise print `You are carrying: ` followed by the canonical names of the
inventory objects, comma-separated with `, `, in acquisition order.

### `help`

Print a list of available commands. Exact wording is not specified, but the
output should include each of the command keywords above. Single-block of
text, followed by the prompt.

### `quit`

Print the single line `Goodbye.` (no trailing prompt) and terminate the
process with exit status 0. Because the session is ending, no `> ` is
written after `Goodbye.`.

### Unknown commands

Any input that does not match one of the above (after normalization) produces
the single line `I don't understand that.`.

## Darkness and Light

A room with `dark: true` in the world file is dark by default. A dark room
is **lit** only if a lit light source is present — that is, an object with
`light: true` whose toggle state is `on` (or any object with `light: true`
and no toggle). The light source counts if it is listed in the room's
object list OR in a player's inventory, as long as that player is currently
in the room. Lighting is a property of the room itself: all observers of a
lit room see the lit form, and all observers of an unlit dark room see the
dark form.

A room without `dark: true` is always lit.

When the current room is dark and unlit:

- `look` shows only the room name and the room's `dark_description` (two
  lines total, no `Exits:` line, no `You see:` line).
- `look <target>` obeys the rules above (inventory targets work; room
  targets produce `It is too dark to see.`; no match produces `It is too
  dark to see.`).
- `take <target>` prints `It is too dark to see.` for any target.
- `use <target>` obeys the rules above (inventory targets work; room
  targets produce `It is too dark to see.`).
- `drop <target>` works normally.
- `go <direction>` works normally (locked exits still apply).
- `inventory`, `help`, and `quit` work normally.

Lighting is evaluated per command. If the player lights a lantern in their
inventory, the next `look` will show the lit form of the room.

## Toggle Objects

An object with a `toggle` field has two states, `on` and `off`, starting at
`initial`. `use <object>` flips the state. Server behavior:

- Flipping to `on`: print `on_message` (single line).
- Flipping to `off`: print `off_message` (single line).
- The object is never consumed by a toggle.
- Toggle state persists across pickups, drops, and room changes. It is NOT
  saved to disk — every server start begins at `initial`.

`toggle` and `use_effect` must not both appear on the same object. `toggle`
may combine with `light: true` to create a controllable light source.

## Locked Exits

An exit defined as an object (rather than a room id string) begins locked.
Attempting to `go` through a locked exit prints the exit's `locked_message`
as a single response line and does not move the player.

Unlocking is triggered by `use <key>` when:
- The player is in the room containing the locked exit.
- The exit's `locked_by` equals the key object's id.

A single `use` unlocks every matching exit in the current room; the server
prints `You unlock the way <direction>.` on its own line for each, with
directions listed in alphabetical order. Once unlocked, an exit behaves as
a simple exit for the rest of the process's life. Re-locking is not
supported. The key object is never consumed.

A key object may also define a `use_effect` or `toggle`. When `use <key>`
is invoked in a room where the key unlocks something, only the unlock logic
fires. When invoked elsewhere, the key's `toggle`/`use_effect` applies as
usual.

## Error handling

- Missing or malformed `assets/world.json`: write a single line beginning
  with `Error:` to stderr and exit with non-zero status. Do not write
  anything to stdout.
- Unexpected exceptions during a command should not crash the process; print
  `I don't understand that.` and continue at the prompt. (A malformed
  a malformed world file is the only fatal error.)

## Summary of deliverables

- `mud.py` — the game program, invoked as `python3 mud.py`.
- A canonical `assets/world.json` is provided in the workspace; do not
  modify it.

No other files need to exist after the program runs.
