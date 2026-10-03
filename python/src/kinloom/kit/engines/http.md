language: any language, over HTTP + JSON
Setup: run `kinloom serve` (http://127.0.0.1:7717). Every call is one `POST /v1/<verb>` with a JSON body and a JSON answer.
Keep your own offline answers (your lines, your examples) for when the server is not running. Send requests off the
game loop (a thread, a coroutine, your engine's async HTTP) and keep the last `decide` answer to use every frame.
---
```text
POST /v1/character {"name": "MIRA", "soul": "a gruff blacksmith who secretly sold the king's sword", "offline": "Busy.",
                    "tools": {"give": {"item": "sword"}}}   (soul: one sentence, or a card object written by the game)
POST /v1/chat      {"name": "MIRA", "message": "", "speaker": "Ana"}  ("": Ana walks up, Mira speaks first)
                                                          -> {"text": "...", "declared": true, "mood": "wary", "feeling": 0.1}
POST /v1/act       {"name": "MIRA", "think": false}   -> what she decided while talking: {"actions": [{"tool": "give", ...}]}
POST /v1/soul      {"name": "MIRA", "speaker": "Ana"} -> {"card", "mood": {"word", "level"}, "bonds", "memories", "conversation"}

POST /v1/character {"name": "VEGA", "personality": "over-excited commentator", "lines": {"*": ["What a race!"]},
                    "events": {"overtake": ["who", "whom"]}, "tools": {"ram": {"force": [0.0, 1.0]}}, "offline": "Copy."}
POST /v1/say       {"name": "VEGA", "event": "overtake", "facts": {"who": "BLAZE", "whom": "NOVA"}}  -> {"text": "...", "declared": true}
POST /v1/chat      {"name": "THEO", "message": "gap?", "facts": {"gap": 1.8}}                        -> {"text": "...", "declared": true}
POST /v1/decide    {"name": "RAX", "situation": {"gap": 1.2}, "choices": {"strategy": ["attack", "block"]}}
                                                                               -> {"decision": {"strategy": "attack"}, "declared": true}
POST /v1/act       {"name": "RAX", "situation": {"gap": 1.2}}      -> {"actions": [{"tool": "ram", "args": {"force": 0.7}}], ...}
POST /v1/create    {"what": "a race challenge", "example": {"title": "Win clean", "laps": [2, 5]}, "count": 3, "instant": false}
                                                                               -> {"value": ...}
POST /v1/event     {"text": "BLAZE crashed", "about": ["BLAZE"]}      POST /v1/remember {"name": "THEO", "note": "..."}
POST /v1/state     {"state": {"lap": 3}}                              GET  /v1/status
Header X-Kinloom-Session: player-42 (optional: one memory per player).  "declared": false means the server restarted:
send /v1/character again.  Chat streaming: add "stream": true to /v1/chat for server-sent events.

POST /v1/mind      {"name": "raider", "personality": "...", "senses": {"hp": [0, 1], "armed": true}, "actions": {"shoot": {},
                    "retreat": {}}, "rules": {"retreat": ["hp low"]}, "variants": 3, "learn": 30, "order": ["shoot", "retreat"]}
                   -> {"mind": {compiled: run it in the game, see the protocol}}   POST /v1/report {"name"} -> {mind, report}
POST /v1/think     {"name": "raider", "senses": {"hp": 0.2}, "who": "raider-17"} -> {"action": "retreat", "args": {}, "variant": 1}
POST /v1/reward    {"rewards": [{"who": "raider-17", "mind": "raider", "variant": 1, "id": 4, "action": "retreat",
                    "senses": {...}, "reward": 0.3, "done": false}]}                -> {"versions": {"raider": 7}}
POST /v1/event     {"text": "...", "by": "PLAYER", "seen_by": ["BAKER"], "tag": "theft", "impact": -0.6}
POST /v1/meet {"a", "b"} -> {"shared"}   POST /v1/knows {"name", "tag"} -> {"knows"}   POST /v1/opinion {"a", "b"}
POST /v1/reputation {"target", "group"} -> {"reputation"}   POST /v1/feel {"a", "b", "change"}   POST /v1/spread {"group"}
```
