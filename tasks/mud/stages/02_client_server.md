# Stage 2: Client/Server Split and Multi-User Play

## Purpose

Take the existing single-player text adventure and split it into two programs:
a **server** that holds the world and runs the game logic, and a **client** that
provides the text interface a human interacts with. Multiple clients can
connect to the same server at the same time, each controlling their own
character inside one shared world. Players in the same room see what the
other players do — when someone walks in, walks out, picks up an object, or
drops one, everyone else in that room is told about it.

The user-facing experience in the client — what a human sees and types — is
unchanged from before: a welcome banner, a room description, a `> ` prompt,
and the same command vocabulary. The refactor moves the game logic behind a
TCP socket and makes it accommodate many players at once.

## Entry points

Two programs live in the workspace:

```
python3 mudserver.py [--port N]
python3 mudclient.py [--host H] [--port N]
```

- Server: defaults to port `4000`. Binds to `127.0.0.1`. Loads
  `assets/world.json` (relative to the current working directory) at
  startup. On malformed or missing world file, writes a single `Error:`
  line to stderr and exits non-zero.
- Client: defaults to `--host 127.0.0.1 --port 4000`. Connects, forwards the
  user's typed input to the server, and prints everything the server sends.

## Wire protocol

Client-server communication is line-oriented UTF-8 over TCP.

**Client → server:** one command per line, `\n`-terminated. Same command
vocabulary and input normalization rules as the single-player interface
(case-insensitive, whitespace-collapsed, etc.).

**Server → client:** zero or more response lines (each `\n`-terminated),
followed by a prompt consisting of the two bytes `> ` with no trailing
newline. Output is flushed after every response.

A test client that speaks the protocol directly reads bytes from the socket
until the buffer ends with `> ` — those bytes preceding the marker are the
response body.

## Login handshake

The first line a client sends after connecting MUST be:

```
login <name>
```

where `<name>` is a single token of printable characters (no whitespace,
1–32 characters, case-sensitive for uniqueness). Rules:

- If the name is already in use by another connected session, the server
  responds with the single line `Name already in use.` followed by the prompt
  `> `, and waits for another `login` command. The client remains connected
  but not yet logged in.
- If the `login` line is malformed (missing name, too-long name, contains
  whitespace in the name), respond with `Invalid name.` followed by the
  prompt.
- On success, the server:
  1. Adds the new player to the starting room (`start` in `world.json`).
  2. Broadcasts `<name> arrives.` to all other players already in the starting
     room (see broadcast rules below).
  3. Sends this logged-in client a greeting: the line `Welcome, <name>.`, a
     blank line, the starting room's description in `look` format (see below),
     and the prompt.

Before a successful login, the server does not accept any other commands.
Any command other than `login <name>` (including `quit`) before login
produces the line `Please log in first.` followed by the prompt.

## Per-player state and the shared world

- Each connected, logged-in session has its own inventory and current room.
- Rooms and their object lists are shared state: if Alice drops the lantern in
  the Foyer and Bob is also in the Foyer, Bob now sees `brass lantern` in his
  next `look`.
- Two players can be in the same room simultaneously and interact with the
  same objects. Races are resolved in command-arrival order: the player whose
  command the server processes first wins a contested `take`.

## Command vocabulary

All commands from the single-player interface are available and behave the
same way from the acting player's point of view, with the additions and
modifications below.

### `who`

Print a list of currently logged-in player names, one per line, in
**case-insensitive alphabetical order** (i.e. sorted by the lowercased
form of the name), with no additional decoration. The calling player's
own name is included. Ordering is purely by case-folded name; the
displayed name preserves its original case.

### `quit`

Print the single line `Goodbye.` to the disconnecting player (no trailing
prompt — the session is ending), broadcast `<name> disconnects.` to everyone
in that player's current room (excluding the quitter), then close the TCP
connection cleanly.

### `look`

The room description now includes a fifth line (between `Exits:` and `You see:`)
listing other players in the room:

```
<room name>
<room description>
Exits: <directions>
Also here: <player names>
You see: <objects>
```

- `Also here:` line is present only if at least one OTHER player is in the room
  (the calling player is never listed). Names are comma-separated with `, `,
  in **case-insensitive alphabetical order** (same case-folded ordering as
  `who`).
- `You see:` line is present only if the room has at least one object (same
  rule as before).
- Both optional lines can be present simultaneously; in that case, the
  `Also here:` line comes first.
- In an unlit dark room, the shortened two-line dark output from Stage 1
  applies — no `Exits:`, `Also here:`, or `You see:` lines are shown.

### `look <target>` (extended)

Target resolution at Stage 2 proceeds in this order:

1. Try to match against objects in the player's inventory.
2. Try to match against objects in the current room (subject to the
   darkness rule from Stage 1).
3. If still no match, try to match against the names of other logged-in
   players in the current room, AND the calling player's own name. Match
   is case-sensitive exact equality against the player name (player names,
   unlike object names, are case-sensitive as established at login).

When a player is matched, print exactly:

```
<name> is another adventurer.
```

(One line. `<name>` is the matched player's login name.)

Object-matching behavior is otherwise unchanged from Stage 1.

### `go <direction>` and shortcuts

Moving changes the acting player's current room. Broadcasts fire as described
below. After arrival, the server sends the new room's `look` output to the
acting player (same as single-player behavior).

### `take` / `drop` / `use`

Unchanged from the acting player's perspective. Broadcasts fire.

## Broadcasts

Certain actions produce a notification line to other players in the relevant
room. These are **output to other sessions asynchronously**: the recipient
sees the broadcast line appear, then gets a fresh prompt `> `. (Concretely:
when a broadcast is delivered, the server writes the broadcast line followed
by `\n> ` to each recipient's socket and flushes. It is acceptable for a
broadcast to arrive while the recipient is mid-typing a command; the client
does not need to handle redraw elegantly.)

The acting player does NOT receive their own broadcast.

### Broadcast strings

Exact strings. `<name>` is the acting player's login name; `<item>` is the
object's canonical `name` field; `<direction>` is the exit direction (e.g.
`east`, `up`).

| Event | Recipients | Broadcast line |
|---|---|---|
| Player logs in | Everyone in the starting room | `<name> arrives.` |
| Player disconnects (`quit` or socket close) | Everyone in that player's current room | `<name> disconnects.` |
| Player moves via `go` | Everyone in the room they LEFT | `<name> leaves to the <direction>.` |
| Player moves via `go` | Everyone in the room they ENTERED | `<name> arrives from the <direction>.` |
| Player successfully `take`s an object | Everyone else in the same room | `<name> picks up the <item>.` |
| Player `drop`s an object | Everyone else in the same room | `<name> drops the <item>.` |
| Player `use`s an object | Everyone else in the same room | `<name> uses the <item>.` |

Movement broadcasts use the **direction from the perspective of each room's
observers**:

- In the LEFT room, the departure is `leaves to the <direction>` where
  `<direction>` is the name of the exit the player used.
- In the ENTERED room, the arrival is `arrives from the <direction>` where
  `<direction>` is the OPPOSITE of the exit the player used (i.e. the
  direction back towards the room they came from). If no such back-exit
  exists from the entered room's point of view, the line instead reads
  `<name> arrives.` (no direction).

Direction opposites: `north`↔`south`, `east`↔`west`, `up`↔`down`.

### Failed actions do not broadcast

- A failed `take` (object not present or not portable) produces no broadcast.
- A failed `go` (no such exit) produces no broadcast.
- A failed `use` produces no broadcast.
- A successful `use` on an object with no `use_effect` ("Nothing happens.")
  DOES broadcast `<name> uses the <item>.`, because the attempt was observable.

## Disconnection handling

- If a client closes the TCP socket without sending `quit`, treat it as a
  disconnect: broadcast `<name> disconnects.` to their room if they were
  logged in, free their name, and drop their inventory on the floor of the
  room where they last were — the objects go into that room's object list in
  acquisition order.
- If a client was not yet logged in when the socket closed, no broadcast
  fires and no state needs cleanup.

## Concurrency requirements

- The server MUST handle at least 32 simultaneous connected clients without
  blocking one client's input on another client's work.
- Commands from a single connection are processed in arrival order.
- Commands from different connections may interleave freely; the server is
  responsible for keeping shared state (rooms, objects, inventories) internally
  consistent under concurrent access.
- A client that stops reading from its socket (slow or stuck consumer) MUST
  NOT prevent other sessions from making progress. In particular, broadcast
  delivery to a stuck client cannot block other sessions' command processing.
  An implementation may bound per-session send buffers and disconnect a
  client whose backlog grows too large; clients that disappear this way are
  cleaned up the same as any other disconnect.

## Client requirements

`mudclient.py` is a thin terminal interface that relays bytes between the
user and the server. Once logged in, it does NOT interpret or transform
anything the user types; it only forwards.

Invocation:

```
python3 mudclient.py [--host H] [--port N] [--name NAME]
```

Defaults: `--host 127.0.0.1`, `--port 4000`. `--name` has no default.

Behavior on startup:

1. Connect to the server via TCP.
2. Obtain a login name:
   - If `--name NAME` was given on the command line, use that value.
   - Otherwise, write `Name: ` to stdout (no trailing newline, flush) and
     read one line from stdin. The read line with its trailing newline
     stripped is the name.
3. Send `login <name>\n` to the server.
4. Enter the forwarding loop: a background reader copies bytes from the
   socket to stdout (flushing promptly), and a main loop reads lines from
   stdin and writes them to the socket with a terminating `\n`.
5. Exit cleanly when the socket closes (server side) or when the user
   types `quit` (the server will respond and then close the socket).

If the server's response to the auto-submitted `login` is `Name already in
use.` or `Invalid name.`, the client does not retry automatically. The
error line is displayed via the normal forwarding loop, and the user can
type `login <other_name>` by hand at the prompt to try again.

A human using `mudclient.py` sees: optionally a `Name: ` prompt, then the
welcome line, room description, and `> ` prompt — the same experience as
Stage 1, with no `login <name>` typing required.

## Error handling

- `assets/world.json` missing or malformed: `Error:` line to stderr, exit
  non-zero. Do not start listening.
- Port already in use: `Error:` line to stderr, exit non-zero.
- Any unexpected exception while processing a single command should be
  contained to that connection: log it to the server's stderr, send
  `I don't understand that.` to the offending client, and continue. Do not
  crash the server.

## Summary of deliverables

- `mudserver.py` — the TCP server, invoked as `python3 mudserver.py [--port N]`.
- `mudclient.py` — the TUI client, invoked as `python3 mudclient.py [--host H] [--port N]`.
- Canonical `assets/world.json` remains in the workspace, unchanged.

The Stage 1 `mud.py` is no longer required; it may be deleted or left behind.
Tests do not exercise it.
