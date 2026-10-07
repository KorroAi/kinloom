"""`kinloom deploy [folder]`: everything needed to run Kinloom online for a shipped game, where players cannot run a
local server and must never get the model key. Writes a self-contained folder (this package, a Dockerfile, a
kinloom.json with caps, DEPLOY.md); it deploys nothing by itself: pushing it to a host is the developer's step."""
import os
import secrets
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))

DOCKERFILE = """FROM python:3.12-slim
WORKDIR /app
COPY kinloom /app/kinloom
COPY kinloom.json /app/kinloom.json
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
# The host sets PORT; the keys come from the host's secrets, never from this folder.
# --trust-proxy: hosts such as Railway and Fly.io put a proxy in front; the player's address comes from its headers.
CMD ["python", "-m", "kinloom.cli", "serve", "--public", "--host", "0.0.0.0", "--quiet", "--trust-proxy"]
"""

CONFIG = """{
  "memory": "/data/memory.json",
  "max_cost_per_hour": 1.0,
  "max_cost_per_day": 10.0,
  "prices": null
}
"""

GUIDE = """# Kinloom online server

Players cannot run `kinloom serve` and must never receive your model key. This folder runs Kinloom on a host you
choose; your game's client talks to it with a **player token**.

## 1. Before deploying

- In `kinloom.json`, set `"prices"` to your model's real prices with their source, e.g.
  `{{"input": 0.30, "output": 1.20, "source": "provider page, read on <date>"}}` (dollars per million tokens). Without
  prices the cost caps (`max_cost_per_hour`, `max_cost_per_day`) cannot be enforced.
- Adjust the caps. Past them, characters answer with their offline lines until the window moves.

## 2. Secrets to set on the host (environment variables, never in files)

| Variable | Value |
|---|---|
| `KINLOOM_SERVER_TOKEN` | the admin token printed by `kinloom deploy` (dashboard, journal; keep it private, never in a file) |
| `KINLOOM_PLAYER_TOKEN` | the player token printed by `kinloom deploy` (goes in the game build) |
| your model key | e.g. `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, or `OPENROUTER_API_KEY` + `KINLOOM_MODEL` |
| your voice key (optional) | `ELEVENLABS_API_KEY` or `OPENAI_API_KEY`: characters speak and players are heard (none: the players' own system voice) |

`kinloom deploy` printed two new tokens once; they are written nowhere. Make new ones any time with
`python -c "import secrets; print(secrets.token_urlsafe(24))"`.

## 3. Deploy (any Docker host)

- Railway: `railway init`, then `railway up` in this folder; add the variables above; add a volume mounted at `/data`.
- Fly.io: `fly launch` (it finds the Dockerfile), `fly secrets set KINLOOM_SERVER_TOKEN=... KINLOOM_PLAYER_TOKEN=...
  <MODEL_KEY>=...`, a volume at `/data`.
- Any server: `docker build -t kinloom . && docker run -p 7717:7717 -e PORT=7717 -e ... -v kinloom-data:/data kinloom`.

## 4. In the game

Point the client at the server with the player token and one session per player (an id you keep for that player:
it holds their memories, bonds and feelings), e.g. JavaScript:
`new Kinloom({{ url: "https://your-host", token: "<player token>", session: playerId }})`; Python (the same game code
as in development): `Kinloom(url="https://your-host", token="<player token>", session=player_id)`, or set `KINLOOM_URL` and
`KINLOOM_TOKEN` in the build's environment.

## What the player token can and cannot do

- It plays: chat, say, decide, act, create, suggest, converse, event, its own characters and minds, speak, listen,
  save and load (only saves this server gave, unchanged).
- By default it may also set what the game decides in its own session (feel, remember, state, steer, tools, lore,
  several speakers): a single-player game is the authority of its own world. It can never change the characters of
  this folder's kinloom.json. Use a random id per player as the session (never "default"): a session is that
  player's world.
- A shared world (players in one session, your own game server holding the admin token): keep these for the server
  with `--player-can none` in the Dockerfile command (or list what players keep, e.g. `--player-can remember`). A
  player then speaks as one speaker per session (the first name it uses) and never reads another's conversation.
- It cannot read the journal, the live stream or the full status (the admin token can: open `https://your-host/#token=...`).
- Requests that start model work (chat, create, characters with a soul...) are limited per player session (30 a
  minute) and per address (60 a minute) by default; polling (decide, act, reads) gets 20 times more
  (`--rate-per-session`, `--rate-per-ip` in the Dockerfile command). Over the limit: 429 with Retry-After, and the
  client answers offline. The address is the player's, read from the proxy's headers (`--trust-proxy`): remove that
  flag if nothing sits in front of the server.
- It sees a character's mood, gesture and summary, never its secrets, inner card or what it knows of other players.
- `GET /healthz` answers `{{"ok": true}}` without a token, for the host's health checks.
- A player token found in a game build can be used by anyone: the limits and the cost caps bound what it can cost.
- The server protects your key, your budget and other players. It cannot stop a modified game client from cheating in
  its own session (the game applies the actions it receives): keep what matters (inventory, money) server-side if your
  game has a server.
  Sessions are not secret: use ids that are hard to guess if players must not read each other's characters.
"""


def _bundle(folder):
    try:
        with open(os.path.join(folder, "README.txt"), encoding="utf-8") as f:
            return f.read(40).startswith("Kinloom for this game")
    except OSError:
        return False


def run(folder="kinloom-deploy"):
    folder = os.path.abspath(folder)
    if os.path.isdir(folder) and _bundle(folder):
        print("%s is a `kinloom bundle` folder that ships with the game: nothing written (the online server needs its "
              "own folder, outside the game: kinloom deploy <folder>)" % folder)
        return 1
    if os.path.exists(folder) and (not os.path.isdir(folder) or os.listdir(folder)):
        print("%s already exists and is not empty: nothing written (choose a new folder, or delete it to start again)"
              % folder)
        return 1
    os.makedirs(folder, exist_ok=True)
    shutil.copytree(HERE, os.path.join(folder, "kinloom"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "clients", "kit", "*.egg-info"))
    with open(os.path.join(folder, "Dockerfile"), "w", encoding="utf-8") as f:
        f.write(DOCKERFILE)
    with open(os.path.join(folder, "kinloom.json"), "w", encoding="utf-8") as f:
        f.write(CONFIG)
    with open(os.path.join(folder, "DEPLOY.md"), "w", encoding="utf-8") as f:
        f.write(GUIDE.format())
    admin, player = secrets.token_urlsafe(24), secrets.token_urlsafe(18)
    print("wrote %s: Dockerfile, kinloom.json, DEPLOY.md, kinloom/" % folder)
    print()
    print("Two new tokens, shown once and written nowhere: set them as secrets on your host (DEPLOY.md, step 2)")
    print("  KINLOOM_SERVER_TOKEN  %s" % admin)
    print("  KINLOOM_PLAYER_TOKEN  %s" % player)
    print()
    print("next: set real prices in kinloom.json, then follow DEPLOY.md (nothing was deployed). Keep this folder out "
          "of the game you ship.")
    return 0
