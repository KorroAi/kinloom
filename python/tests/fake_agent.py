"""A stand-in for a coding agent's command line (tests never start a real one). It reads the prompt the way each
agent gets it, writes what it received to FAKE_AGENT_LOG (one JSON line per call) and answers FAKE_AGENT_ANSWER in
that agent's output format:

    claude   stream-json in and out (-p --input-format stream-json ...)   codex    exec, answer in the -o FILE
    gemini   -p INSTRUCTION, prompt on stdin, answer on stdout             opencode run MESSAGE -f PROMPTFILE
    plain    anything else: stdin in, stdout out (provider "command")
FAKE_AGENT_SLEEP: seconds to wait before answering (deadlines); FAKE_AGENT_FAIL: exit 3 with a message on stderr.
"""
import json
import os
import sys
import time

argv = sys.argv[1:]
answer = os.environ.get("FAKE_AGENT_ANSWER", "Hello there.")
log = os.environ.get("FAKE_AGENT_LOG")


def record(kind, prompt, extra=None):
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict({"kind": kind, "argv": argv, "prompt": prompt, "cwd": os.getcwd()}, **(extra or {}))) + "\n")


def wait():
    time.sleep(float(os.environ.get("FAKE_AGENT_SLEEP", "0") or 0))


if os.environ.get("FAKE_AGENT_FAIL"):
    sys.stdin.read()
    sys.stderr.write("not logged in: run the agent once to sign in\n")
    sys.exit(3)

if "--input-format" in argv:                                   # claude-code
    raw = sys.stdin.readline()
    wait()
    message = json.loads(raw)
    content = message["message"]["content"]
    text = "".join(c.get("text", "") for c in content if c.get("type") == "text")
    images = [c["source"]["media_type"] for c in content if c.get("type") == "image"]
    record("claude", text, {"images": images})
    out = sys.stdout
    out.write(json.dumps({"type": "system", "subtype": "init"}) + "\n")
    out.write("a line that is not JSON\n")
    for i in range(0, len(answer), 5):
        out.write(json.dumps({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0,
                                                                "delta": {"type": "text_delta", "text": answer[i:i + 5]}}}) + "\n")
        out.flush()
    out.write(json.dumps({"type": "stream_event", "event": {"type": "content_block_delta",
                                                            "delta": {"type": "thinking_delta", "thinking": "hmm"}}}) + "\n")
    out.write(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": answer,
                          "usage": {"input_tokens": 100, "cache_read_input_tokens": 20, "output_tokens": 7}}) + "\n")
    out.flush()
elif argv[:1] == ["exec"]:                                     # codex
    prompt = sys.stdin.read()
    wait()
    images = [argv[i + 1] for i, a in enumerate(argv) if a == "-i"]
    record("codex", prompt, {"images": [os.path.exists(x) for x in images]})
    target = argv[argv.index("-o") + 1]
    print("codex: working...")
    with open(target, "w", encoding="utf-8") as f:
        f.write(answer)
elif argv[:1] == ["-p"]:                                       # gemini
    prompt = sys.stdin.read()
    wait()
    record("gemini", prompt + "\n" + argv[1])
    print(answer)
elif argv[:1] == ["run"]:                                      # opencode
    files = [argv[i + 1] for i, a in enumerate(argv) if a == "-f"]
    with open(files[0], encoding="utf-8") as f:
        prompt = f.read()
    wait()
    record("opencode", prompt, {"message": argv[1], "files": len(files)})
    print("\x1b[1m" + answer + "\x1b[0m")
else:                                                          # any command
    prompt = sys.stdin.read()
    wait()
    record("plain", prompt)
    print(answer)
